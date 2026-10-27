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


POKRYCIE = (0.10, 0.90)               # przedział P10–P90: ok. 80% dni (i sum) w środku
METODY = ("model", "kalendarz", "srednia")
OPISY = {"model": "model ML (kalendarz, sezon, klimatologia)", "kalendarz": "poziom × profil kalendarza (dzień tygodnia, dni wolne)",
         "srednia": "średnia z ostatnich 4 tygodni"}


def _kubel(dni):
    return np.select([dni <= 7, dni <= 14, dni <= 30], ["1–7", "8–14", "15–30"], "31–60")


def _podzial_kal(t, q=0.8):
    """Odłożone 20% najpóźniejszych startów (per pompownia) do wyboru metody i przedziałów; uczenie na dniach przed nimi."""
    g = t.groupby("obiekt_id")["start"].transform(lambda s: s.quantile(q))
    return t[t["dzien"] < g], t[t["start"] >= g]


def _profil(tr):
    """Współczynnik dnia: mediana (zużycie / poziom z 28 dni) per pompownia, dzień tygodnia i dzień wolny."""
    r = tr.assign(r=tr["kwh"] / tr["poziom"], wolny=tr["dzien_wolny"].fillna(0))
    p = r.groupby(["obiekt_id", "dzien_tyg", "wolny"])["r"].median().rename("f").reset_index()
    return p


def _p50(metoda, m, t, X, profil):
    if metoda == "model":
        q = np.expm1(np.clip(m.predict(t[X]), 0, None))
        return np.sort(q, axis=1)[:, 1] * t["poziom"].values
    if metoda == "kalendarz":
        k = t.assign(wolny=t["dzien_wolny"].fillna(0)).merge(profil, on=["obiekt_id", "dzien_tyg", "wolny"], how="left")
        return k["f"].fillna(1.0).values * t["poziom"].values
    return t["poziom"].values.astype(float)


def _wape(kwh, p):
    return float(100 * np.abs(np.asarray(p) - kwh).sum() / kwh.sum())


MIN_DNI, MIN_SUM = 60, 8              # mniej obserwacji pompowni w kuble -> przedział wspólny wszystkich pompowni


def _kw(x):
    return [float(x.quantile(POKRYCIE[0])), float(x.quantile(POKRYCIE[1]))]


def _przedzialy(kal, p50):
    """Empiryczne kwantyle (prawda / P50) per horyzont i per pompownia (spokojna pompownia nie dziedziczy niepewności
    pompowni z gwałtownymi szczytami po ulewach) + dla sum 7 i 30 dni. Zapas: wartości wspólne wszystkich pompowni."""
    r = kal.assign(p50=p50, kubel=_kubel(kal["dni"].values), ratio=kal["kwh"] / p50)
    dz = {"wspolne": {k: _kw(g["ratio"]) for k, g in r.groupby("kubel")}, "obiekty": {}}
    for (oid, k), g in r.groupby(["obiekt_id", "kubel"]):
        if len(g) >= MIN_DNI:
            dz["obiekty"].setdefault(oid, {})[k] = _kw(g["ratio"])
    sumy = {"wspolne": {}, "obiekty": {}}
    for n in (7, 30):
        okna = r[r["dni"] <= n].groupby(["obiekt_id", "start"]).filter(lambda x: len(x) == n)
        sm = okna.groupby(["obiekt_id", "start"])[["kwh", "p50"]].sum().reset_index()
        sm["ratio"] = sm["kwh"] / sm["p50"]
        if len(sm) >= MIN_SUM:
            sumy["wspolne"][str(n)] = _kw(sm["ratio"])
        for oid, g in sm.groupby("obiekt_id"):
            if len(g) >= MIN_SUM:
                sumy["obiekty"].setdefault(oid, {})[str(n)] = _kw(g["ratio"])
    return {"dzienne": dz, "sumy": sumy}


def _q(tabela, oid, klucz, domyslnie=(1.0, 1.0)):
    """Kwantyle dla pompowni (gdy policzone), inaczej wspólne (stary format meta: słownik bez podziału)."""
    if "wspolne" not in tabela:
        return tabela.get(klucz, list(domyslnie))
    return tabela["obiekty"].get(oid, {}).get(klucz) or tabela["wspolne"].get(klucz, list(domyslnie))


PUNKTY_KAL = (0.4, 0.55, 0.7, 0.85)   # okresy kroczące w części treningowej (ułamki startów per pompownia)


def _wybierz(t, X):
    """Wybór metody P50 i przedziałów na prognozach „poza próbą” z kilku okresów kroczących w części treningowej:
    dla okresu i model uczony na dniach przed jego początkiem, oceniany na startach z tego okresu (bez zaglądania w test)."""
    czesci = []
    for a, b in zip(PUNKTY_KAL, PUNKTY_KAL[1:] + (1.01,)):
        od = t.groupby("obiekt_id")["start"].transform(lambda s: s.quantile(a))
        do = t.groupby("obiekt_id")["start"].transform(lambda s: s.quantile(min(b, 1.0))) if b <= 1 else t["start"] + pd.Timedelta(days=1)
        ucz, kal = t[t["dzien"] < od], t[(t["start"] >= od) & (t["start"] < do)]
        if len(ucz) < 1000 or kal.empty:
            continue
        m = xgb.XGBRegressor(**PARAMS).fit(ucz[X], ucz["y_log"], verbose=False)
        prof = _profil(ucz)
        czesci.append(kal.assign(okres=len(czesci), **{f"p_{me}": _p50(me, m, kal, X, prof) for me in METODY}))
    if not czesci:                                                  # za mało danych - średnia z 4 tygodni, przedziały ±
        return "srednia", {}, {"dzienne": {}, "sumy": {}}
    oos = pd.concat(czesci, ignore_index=True)
    wyniki = {me: _wape(oos["kwh"].values, oos[f"p_{me}"]) for me in METODY}
    metoda = min(wyniki, key=wyniki.get)
    przedzialy = _przedzialy(oos, oos[f"p_{metoda}"].values)
    przedzialy["poszerzenie"] = _poszerzenie(oos, metoda)
    return metoda, wyniki, przedzialy


KUBLY = ("1–7", "8–14", "15–30", "31–60")


def _granice(lo_hi, s):
    lo, hi = lo_hi
    return np.exp(s * np.log(min(lo, 1))), np.exp(s * np.log(max(hi, 1)))


def _granice_wierszy(df, q_dzienne, s_kubla):
    """Mnożniki P10 / P90 dla każdego wiersza (pompownia, horyzont)."""
    k = _kubel(df["dni"].values)
    gr = [_granice(_q(q_dzienne, o, x), s_kubla.get(x, 1.0) if isinstance(s_kubla, dict) else s_kubla)
          for o, x in zip(df["obiekt_id"].values, k)]
    return np.array([g[0] for g in gr]), np.array([g[1] for g in gr])


def _poszerzenie(oos, metoda):
    """Krokowo, osobno dla każdego przedziału dni: przedział z okresów 0..j-1 sprawdzany na okresie j; najmniejsze
    poszerzenie (w skali log), przy którym średnie pokrycie >= 80%. Uwzględnia niepewność rosnącą z horyzontem."""
    okresy = sorted(oos["okres"].unique())
    oos = oos.assign(kubel=_kubel(oos["dni"].values))
    wynik, cache = {}, {}
    for k in KUBLY:
        wynik[k] = 1.0
        if len(okresy) < 2:
            continue
        for s in np.arange(1.0, 4.01, 0.05):
            pokr = []
            for j in okresy[1:]:
                wcz, nast = oos[oos["okres"] < j], oos[(oos["okres"] == j) & (oos["kubel"] == k)]
                if nast.empty:
                    continue
                q = cache.setdefault(j, _przedzialy(wcz, wcz[f"p_{metoda}"].values)["dzienne"])
                lo, hi = _granice_wierszy(nast, q, s)
                p = nast[f"p_{metoda}"].values
                pokr.append(((nast["kwh"].values >= p * lo) & (nast["kwh"].values <= p * hi)).mean())
            if not pokr or np.mean(pokr) >= POKRYCIE[1] - POKRYCIE[0]:
                wynik[k] = float(round(s, 2))
                break
        else:
            wynik[k] = 4.0
    return wynik


def _zastosuj(t, p50, przedzialy):
    lo, hi = _granice_wierszy(t, przedzialy["dzienne"], przedzialy.get("poszerzenie", {}))
    return t.assign(p50=p50, p10=p50 * lo, p90=p50 * hi)


def trenuj(d, zapisz=True, katalog=None):
    from .prognoza import MODELE
    dz, stacje, klim, kal, ob = _przygotuj(d)
    t = proby(dz, stacje, klim, kal, ob)
    X = kolumny(t)
    metoda, wyniki, przedzialy = _wybierz(t, X)
    m = xgb.XGBRegressor(**PARAMS).fit(t[X], t["y_log"], verbose=False)
    prof = _profil(t)
    meta = dict(model="dlugoterminowy", kolumny=X, obiekty=ob, horyzont_dni=HORYZONT_DNI, kwantyle=KWANTYLE, wierszy=int(len(t)),
                metoda=metoda, opis_metody=OPISY[metoda], wape_kalibracja={k: round(v, 2) for k, v in wyniki.items()},
                przedzialy=przedzialy, profil=prof.to_dict(orient="records"),
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


def _sumy(t, okres, przedzialy, n, oid=None):
    g = t.groupby(okres).agg(od=("dzien", "min"), do=("dzien", "max"), dni_w_okresie=("dzien", "count"), p50=("p50", "sum"))
    q = _q(przedzialy["sumy"], oid, str(n), (None, None)) if przedzialy.get("sumy") else None
    q = q if q and q[0] is not None else None
    sz = przedzialy.get("poszerzenie", {})
    s = (sz.get("1–7" if n <= 7 else "15–30", 1.0) if isinstance(sz, dict) else sz)
    if q:
        g["p10"] = g["p50"] * np.exp(s * np.log(min(q[0], 1)))
        g["p90"] = g["p50"] * np.exp(s * np.log(max(q[1], 1)))
    else:                                                            # za mało danych do kalibracji sum - suma dziennych granic
        g["p10"], g["p90"] = t.groupby(okres)["p10"].sum(), t.groupby(okres)["p90"].sum()
    return g.reset_index()


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
    metoda = meta.get("metoda", "model")
    prof = pd.DataFrame(meta.get("profil", []))
    if metoda == "kalendarz" and (prof.empty or oid not in set(prof["obiekt_id"])):
        metoda = "srednia"                                           # nowa pompownia bez profilu - poziom z 28 dni
    t = _zastosuj(t, _p50(metoda, m, t, meta["kolumny"], prof), meta["przedzialy"])
    t = t[["dzien", "dni", "p10", "p50", "p90", "dzien_wolny", "swieto"]]
    tyg = _sumy(t.assign(tydzien=(t["dni"] - 1) // 7 + 1), "tydzien", meta["przedzialy"], 7, oid).drop(columns="dni_w_okresie")
    mies = _sumy(t.assign(miesiac=t["dzien"].dt.to_period("M").astype(str)), "miesiac", meta["przedzialy"], 30, oid) \
        .rename(columns={"dni_w_okresie": "dni"}).drop(columns=["od", "do"])
    return t, tyg, mies, start


def ocena(d, katalog=None):
    """Uczciwa ocena: dla każdej pompowni ostatnie 30% czasu to starty testowe; wybór metody i przedziały - tylko na
    części treningowej (odłożone 20% jej startów), test otwierany raz."""
    dz, stacje, klim, kal, ob = _przygotuj(d)
    t = proby(dz, stacje, klim, kal, ob)
    granica = dz.groupby("obiekt_id")["dzien"].quantile(0.7)
    g = t["obiekt_id"].map(granica)
    tr, te = t[t["dzien"] < g], t[t["start"] >= g].copy()
    X = kolumny(t)
    metoda, wyniki_kal, przedzialy = _wybierz(tr, X)
    m = xgb.XGBRegressor(**PARAMS).fit(tr[X], tr["y_log"], verbose=False)
    prof = _profil(tr)
    for me in METODY:
        te[f"p_{me}"] = _p50(me, m, te, X, prof)
    te = _zastosuj(te, te[f"p_{metoda}"].values, przedzialy)
    te["rok_temu_kwh"] = te["rok_temu"] * te["poziom"]
    szer_ob = (te.assign(s=(te["p90"] - te["p10"]) / te["p50"]).groupby("obiekt_id")["s"].median() * 100).round(0).to_dict()
    wiersze = []
    for k in KUBLY:
        s = te[_kubel(te["dni"].values) == k]
        r = s.dropna(subset=["rok_temu_kwh"])
        wiersze.append(dict(dni=k, plan=_wape(s["kwh"].values, s["p50"]), model_ml=_wape(s["kwh"].values, s["p_model"]),
                            kalendarz=_wape(s["kwh"].values, s["p_kalendarz"]), jak_ostatnie_4tyg=_wape(s["kwh"].values, s["p_srednia"]),
                            rok_temu=_wape(r["kwh"].values, r["rok_temu_kwh"]) if len(r) else np.nan,
                            pokrycie_p10_p90=float(100 * ((s["kwh"] >= s["p10"]) & (s["kwh"] <= s["p90"])).mean())))
    pelne = te[te["dni"] <= 30].groupby(["obiekt_id", "start"]).filter(lambda x: len(x) == 30)
    sumy = pelne.groupby(["obiekt_id", "start"])[["kwh", "p50", "p_srednia"]].sum().reset_index()
    sz = przedzialy.get("poszerzenie", {}).get("15–30", 1.0)
    gr = [_granice(_q(przedzialy["sumy"], o, "30", (1.0, 1.0)), sz) for o in sumy["obiekt_id"]]
    sumy["lo"], sumy["hi"] = [g[0] for g in gr], [g[1] for g in gr]
    q = [0, 0]
    podsum = dict(metoda=metoda, opis_metody=OPISY[metoda], poszerzenie=przedzialy.get("poszerzenie", 1.0), wape_kalibracja={k: round(v, 2) for k, v in wyniki_kal.items()},
                  blad_sumy_30d=float(100 * ((sumy["p50"] - sumy["kwh"]).abs() / sumy["kwh"]).mean()) if len(sumy) else np.nan,
                  blad_sumy_30d_jak_ostatnie_4tyg=float(100 * ((sumy["p_srednia"] - sumy["kwh"]).abs() / sumy["kwh"]).mean()) if len(sumy) else np.nan,
                  pokrycie_sumy_30d=float(100 * ((sumy["kwh"] >= sumy["p50"] * sumy["lo"]) & (sumy["kwh"] <= sumy["p50"] * sumy["hi"])).mean())
                  if len(sumy) else np.nan,
                  startow_testowych=int(te.groupby(["obiekt_id", "start"]).ngroups),
                  szerokosc_przedzialu_proc_p50=szer_ob)
    return pd.DataFrame(wiersze), podsum


def main_ocena(d=None):
    if d is None:
        from .dane import wczytaj
        d = wczytaj()
    t, p = ocena(d)
    print("== Plan na 2 miesiące – ocena na startach testowych (ostatnie 30% czasu każdej pompowni)")
    print(f"  wybrana metoda (na odłożonych startach z treningu): {p['opis_metody']}  "
          f"| błąd przy wyborze: {', '.join(f'{k} {v}%' for k, v in p['wape_kalibracja'].items())}")
    print(t.round(1).to_string(index=False))
    print(f"\n  suma 30 dni od startu: błąd planu {p['blad_sumy_30d']:.1f}% vs „średnia z 4 tygodni” "
          f"{p['blad_sumy_30d_jak_ostatnie_4tyg']:.1f}% | prawdziwa suma w przedziale P10–P90 w {p['pokrycie_sumy_30d']:.0f}% "
          f"przypadków | startów testowych: {p['startow_testowych']}")
    WYNIKI.mkdir(parents=True, exist_ok=True)
    t.round(2).to_csv(WYNIKI / "dlugi.csv", index=False)
    (WYNIKI / "dlugi_podsumowanie.json").write_text(json.dumps({k: round(v, 2) if isinstance(v, float) else v for k, v in p.items()},
                                                               indent=2), encoding="utf-8")
    print(f"\nWyniki: {WYNIKI / 'dlugi.csv'}")
    return t, p
