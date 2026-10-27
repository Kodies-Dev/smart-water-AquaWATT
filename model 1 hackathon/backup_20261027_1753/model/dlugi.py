"""Plan na 2 miesiące: dobowe zużycie energii na 1–60 dni naprzód z przedziałem P10–P90 (bez prognozy pogody).

    python main.py horyzont --dlugi          ocena na wielu datach startu (test) → wyniki/dlugi.csv, wyniki/dlugi.png
    python main.py prognoza --trenuj --dni 7 trenuje też ten model (modele/dlugoterminowy.json)

Dlaczego tak: pogody na tygodnie naprzód nikt nie zna, ale znamy kalendarz, porę roku, ostatni poziom pompowni
i TYPOWĄ pogodę dla danego dnia roku (klimatologia z 2023–2026). Model dzienny XGBoost z regresją kwantylową
(P10, P50, P90) uczony na „datach startu” co 3 dni: dla startu o i dnia t = o+1..o+60 cechy znane w dniu o.
Wynik dzienny służy do planowania sum tygodniowych i miesięcznych (budżet, zakup energii), nie do pojedynczych godzin.
"""
import json
from datetime import datetime

import numpy as np
import pandas as pd
import xgboost as xgb

from .config import TZ, WYNIKI

HORYZONT_DNI = 60
KROK_STARTU = 3                       # co ile dni nowa data startu w treningu
KWANTYLE = [0.1, 0.5, 0.9]
KAL = ["dzien_wolny", "swieto", "mostek", "ferie_zimowe", "wakacje", "przerwa_swiateczna"]
PARAMS = dict(n_estimators=400, learning_rate=0.05, max_depth=5, min_child_weight=20, subsample=0.8,
              colsample_bytree=0.8, tree_method="hist", objective="reg:quantileerror", quantile_alpha=KWANTYLE)


def dobowo(energia):
    """Pełne doby (≥ 23 h) per pompownia: obiekt_id, dzien (data lokalna), kwh."""
    e = energia.dropna(subset=["kwh"]).assign(dzien=lambda x: x["czas"].dt.tz_convert(TZ).dt.date)
    g = e.groupby(["obiekt_id", "dzien"])["kwh"].agg(["sum", "count"])
    g = g[g["count"] >= 23]["sum"].rename("kwh").reset_index()
    g["dzien"] = pd.to_datetime(g["dzien"])
    return g


def klimatologia(pogoda):
    """Typowa pogoda dla dnia roku per punkt pogody: średni opad, szansa deszczu (>1 mm), średnia temperatura (±7 dni)."""
    p = pogoda.assign(dzien=lambda x: x["czas"].dt.tz_convert(TZ).dt.date)
    dz = p.groupby(["stacja", "dzien"]).agg(opad=("opad_mm", "sum"), temp=("temp_c", "mean")).reset_index()
    dz["doy"] = pd.to_datetime(dz["dzien"]).dt.day_of_year.clip(upper=365)
    wynik = []
    for st, g in dz.groupby("stacja"):
        doy = g.groupby("doy").agg(opad=("opad", "mean"), deszcz=("opad", lambda s: (s > 1).mean()), temp=("temp", "mean"))
        doy = doy.reindex(range(1, 366)).interpolate(limit_direction="both")
        sz = pd.concat([doy.iloc[-7:], doy, doy.iloc[:7]]).rolling(15, center=True, min_periods=1).mean().iloc[7:-7]
        wynik.append(sz.assign(stacja=st).reset_index())
    return pd.concat(wynik, ignore_index=True).rename(columns={"opad": "opad_klim", "deszcz": "p_deszczu", "temp": "temp_klim"})


def _kalendarz(kal):
    k = kal.copy()
    k["dzien"] = pd.to_datetime(k["data"])
    for c in KAL:
        k[c] = k[c].astype(float)
    return k[["dzien", *KAL]]


def proby(dz, stacje, klim, kal, obiekty, starty=None, horyzont=HORYZONT_DNI, krok=KROK_STARTU, tylko_znane=True):
    """Wiersze (start, dzień docelowy): cechy znane w dniu startu + kalendarz i klimatologia dnia docelowego."""
    wiersze = []
    for oid, g in dz.groupby("obiekt_id"):
        s = g.set_index("dzien")["kwh"].asfreq("D")
        if starty is None:
            st_ = s.index[35:][::krok]
        else:
            st_ = [starty[oid]] if oid in starty else []
        for o in st_:
            hist = s[:o].dropna()
            if len(hist) < 28:
                continue
            poziom = hist.iloc[-28:].median()
            zmiana = hist.iloc[-7:].median() / poziom
            cele = pd.date_range(o + pd.Timedelta(days=1), periods=horyzont, freq="D")
            r = pd.DataFrame({"obiekt_id": oid, "start": o, "dzien": cele, "dni": np.arange(1, horyzont + 1),
                              "poziom": poziom, "zmiana": zmiana})
            rok = s.reindex(cele - pd.Timedelta(days=364))
            poziom_rok = s[:o - pd.Timedelta(days=364)].dropna().iloc[-28:].median() if len(s[:o - pd.Timedelta(days=364)].dropna()) >= 14 else np.nan
            r["rok_temu"] = rok.values / poziom_rok if pd.notna(poziom_rok) else np.nan
            r["kwh"] = s.reindex(cele).values
            if tylko_znane:
                r = r.dropna(subset=["kwh"])
            wiersze.append(r)
    if not wiersze:
        return pd.DataFrame()
    t = pd.concat(wiersze, ignore_index=True)
    t["stacja"] = t["obiekt_id"].map(stacje)
    t["doy"] = t["dzien"].dt.day_of_year.clip(upper=365)
    t = t.merge(klim, on=["stacja", "doy"], how="left").merge(kal, on="dzien", how="left")
    t["dzien_tyg"], t["miesiac"] = t["dzien"].dt.day_of_week, t["dzien"].dt.month
    t["doy_sin"], t["doy_cos"] = np.sin(2 * np.pi * t["doy"] / 365.25), np.cos(2 * np.pi * t["doy"] / 365.25)
    for oid in obiekty:
        t[f"ob_{oid}"] = (t["obiekt_id"] == oid).astype(float)
    t["y_log"] = np.log1p(t["kwh"] / t["poziom"])
    return t


def kolumny(t):
    return ["dni", "zmiana", "rok_temu", "opad_klim", "p_deszczu", "temp_klim", "dzien_tyg", "miesiac", "doy_sin", "doy_cos",
            *KAL, *[c for c in t if c.startswith("ob_")]]


def _przygotuj(d):
    stacje = d["obiekty"].set_index("obiekt_id")["stacja_pogody"].to_dict()
    return dobowo(d["energia"]), stacje, klimatologia(d["pogoda"]), _kalendarz(d["kalendarz"]), sorted(stacje)


POKRYCIE = 0.80                       # przedział P10–P90 ma obejmować prawdziwą wartość w 80% dni


def _prognoza(m, t, X, szerokosc=1.0):
    """Kwantyle P10/P50/P90; szerokosc > 1 poszerza przedział wokół P50 (kalibracja do 80% pokrycia)."""
    q = np.expm1(np.clip(m.predict(t[X]), 0, None)) * t["poziom"].values[:, None]
    q.sort(axis=1)                                                   # kwantyle bez krzyżowania
    p50 = q[:, 1]
    return t.assign(p10=np.clip(p50 - szerokosc * (p50 - q[:, 0]), 0, None), p50=p50, p90=p50 + szerokosc * (q[:, 2] - p50))


def _kalibruj(t, X):
    """Szerokość przedziału dobrana na odłożonych 20% startów (najpóźniejszych) tak, by pokrycie wyniosło 80%."""
    granica = t.groupby("obiekt_id")["start"].transform(lambda s: s.quantile(0.8))
    ucz, kal = t[t["dzien"] < granica], t[t["start"] >= granica]
    if len(kal) < 100 or len(ucz) < 1000:
        return 1.0
    m = xgb.XGBRegressor(**PARAMS).fit(ucz[X], ucz["y_log"], verbose=False)
    for s in np.arange(1.0, 6.01, 0.1):
        p = _prognoza(m, kal, X, s)
        if ((p["kwh"] >= p["p10"]) & (p["kwh"] <= p["p90"])).mean() >= POKRYCIE:
            return float(round(s, 2))
    return 6.0


def trenuj(d, zapisz=True, katalog=None):
    from .prognoza import MODELE
    dz, stacje, klim, kal, ob = _przygotuj(d)
    t = proby(dz, stacje, klim, kal, ob)
    X = kolumny(t)
    szer = _kalibruj(t, X)
    m = xgb.XGBRegressor(**PARAMS).fit(t[X], t["y_log"], verbose=False)
    meta = dict(model="dlugoterminowy", kolumny=X, obiekty=ob, horyzont_dni=HORYZONT_DNI, kwantyle=KWANTYLE, wierszy=int(len(t)),
                szerokosc_przedzialu=szer, pokrycie_docelowe=POKRYCIE,
                wytrenowano=datetime.now().isoformat(timespec="seconds"))
    if zapisz:
        k = katalog or MODELE
        k.mkdir(parents=True, exist_ok=True)
        m.save_model(k / "dlugoterminowy.json")
        (k / "dlugoterminowy_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return m, meta


def wczytaj_model(katalog=None):
    from .prognoza import MODELE
    k = katalog or MODELE
    if not (k / "dlugoterminowy.json").exists():
        raise FileNotFoundError("Brak modelu długoterminowego. Uruchom: python main.py prognoza --trenuj --dni 7")
    m = xgb.XGBRegressor()
    m.load_model(k / "dlugoterminowy.json")
    return m, json.loads((k / "dlugoterminowy_meta.json").read_text(encoding="utf-8"))


def prognoza(d, oid, nowe=None, stacja=None, dni=HORYZONT_DNI):
    """Plan dobowy na 1..dni od ostatniej pełnej doby (baza + plik). Zwraca dzienne P10/P50/P90, tygodnie, miesiące."""
    m, meta = wczytaj_model()
    e = d["energia"][d["energia"]["obiekt_id"] == oid][["obiekt_id", "czas", "kwh"]]
    if nowe is not None and len(nowe):
        e = pd.concat([e[~e["czas"].isin(nowe["czas"])], nowe.assign(obiekt_id=oid)[["obiekt_id", "czas", "kwh"]]])
    dz = dobowo(e)
    if len(dz) < 28:
        raise ValueError(f"Za mało pełnych dób dla {oid}: {len(dz)}, potrzeba co najmniej 28.")
    ob = d["obiekty"].set_index("obiekt_id")
    stacje = {oid: stacja or (ob.loc[oid, "stacja_pogody"] if oid in ob.index else "RY")}
    start = dz["dzien"].max()
    t = proby(dz, stacje, klimatologia(d["pogoda"]), _kalendarz(d["kalendarz"]), meta["obiekty"], starty={oid: start},
              horyzont=dni, tylko_znane=False)
    for c in meta["kolumny"]:
        if c not in t:
            t[c] = 0.0
    t = _prognoza(m, t, meta["kolumny"], meta.get("szerokosc_przedzialu", 1.0))[["dzien", "dni", "p10", "p50", "p90", "dzien_wolny", "swieto"]]
    tyg = t.assign(tydzien=(t["dni"] - 1) // 7 + 1).groupby("tydzien").agg(
        od=("dzien", "min"), do=("dzien", "max"), p50=("p50", "sum"), p10=("p10", "sum"), p90=("p90", "sum")).reset_index()
    mies = t.assign(miesiac=t["dzien"].dt.to_period("M").astype(str)).groupby("miesiac").agg(
        dni=("dzien", "count"), p50=("p50", "sum"), p10=("p10", "sum"), p90=("p90", "sum")).reset_index()
    return t, tyg, mies, start


def ocena(d, katalog=None):
    """Uczciwa ocena: dla każdej pompowni ostatnie 30% czasu to starty testowe; model uczony tylko na dniach przed nimi."""
    dz, stacje, klim, kal, ob = _przygotuj(d)
    t = proby(dz, stacje, klim, kal, ob)
    granica = dz.groupby("obiekt_id")["dzien"].quantile(0.7)
    g = t["obiekt_id"].map(granica)
    tr, te = t[t["dzien"] < g], t[t["start"] >= g]
    X = kolumny(t)
    szer = _kalibruj(tr, X)                                          # kalibracja tylko na części treningowej
    m = xgb.XGBRegressor(**PARAMS).fit(tr[X], tr["y_log"], verbose=False)
    te = _prognoza(m, te, X, szer).assign(jak_ostatnie_4tyg=lambda x: x["poziom"])
    te["rok_temu_kwh"] = te["rok_temu"] * te["poziom"]
    przedzialy = [(1, 7), (8, 14), (15, 30), (31, 60)]
    wiersze = []
    for a, b in przedzialy:
        s = te[te["dni"].between(a, b)]
        w = lambda k: float(100 * (s[k] - s["kwh"]).abs().sum() / s["kwh"].sum())
        r = s.dropna(subset=["rok_temu_kwh"])
        wiersze.append(dict(dni=f"{a}–{b}", model_p50=w("p50"), jak_ostatnie_4tyg=w("jak_ostatnie_4tyg"),
                            rok_temu=float(100 * (r["rok_temu_kwh"] - r["kwh"]).abs().sum() / r["kwh"].sum()) if len(r) else np.nan,
                            pokrycie_p10_p90=float(100 * ((s["kwh"] >= s["p10"]) & (s["kwh"] <= s["p90"])).mean())))
    # suma 30 dni od startu (budżet miesięczny)
    pelne = te[te["dni"] <= 30].groupby(["obiekt_id", "start"]).filter(lambda x: len(x) == 30)
    sumy = pelne.groupby(["obiekt_id", "start"])[["kwh", "p50", "p10", "p90", "jak_ostatnie_4tyg"]].sum()
    blad_sumy = float(100 * ((sumy["p50"] - sumy["kwh"]).abs() / sumy["kwh"]).mean()) if len(sumy) else np.nan
    blad_sumy_flat = float(100 * ((sumy["jak_ostatnie_4tyg"] - sumy["kwh"]).abs() / sumy["kwh"]).mean()) if len(sumy) else np.nan
    pokrycie_sumy = float(100 * ((sumy["kwh"] >= sumy["p10"]) & (sumy["kwh"] <= sumy["p90"])).mean()) if len(sumy) else np.nan
    wynik = pd.DataFrame(wiersze)
    podsum = dict(blad_sumy_30d=blad_sumy, blad_sumy_30d_jak_ostatnie_4tyg=blad_sumy_flat, pokrycie_sumy_30d=pokrycie_sumy,
                  startow_testowych=int(te.groupby(["obiekt_id", "start"]).ngroups), szerokosc_przedzialu=szer)
    return wynik, podsum


def main_ocena(d=None):
    if d is None:
        from .dane import wczytaj
        d = wczytaj()
    t, p = ocena(d)
    print("== Plan na 2 miesiące – ocena na startach testowych (ostatnie 30% czasu każdej pompowni)")
    print(t.round(1).to_string(index=False))
    print(f"\n  suma 30 dni od startu: błąd modelu {p['blad_sumy_30d']:.1f}% vs „średnia z 4 tygodni” "
          f"{p['blad_sumy_30d_jak_ostatnie_4tyg']:.1f}% | prawdziwa suma w przedziale P10–P90 w {p['pokrycie_sumy_30d']:.0f}% "
          f"przypadków | startów testowych: {p['startow_testowych']}")
    WYNIKI.mkdir(parents=True, exist_ok=True)
    t.round(2).to_csv(WYNIKI / "dlugi.csv", index=False)
    (WYNIKI / "dlugi_podsumowanie.json").write_text(json.dumps({k: round(v, 2) if isinstance(v, float) else v for k, v in p.items()},
                                                               indent=2), encoding="utf-8")
    print(f"\nWyniki: {WYNIKI / 'dlugi.csv'}")
    return t, p
