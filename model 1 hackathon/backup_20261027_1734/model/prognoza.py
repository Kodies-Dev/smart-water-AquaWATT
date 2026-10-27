"""Tryb prognozy – model gotowy do pracy.

    python main.py prognoza --trenuj                       trenuje model na WSZYSTKICH danych z bazy i zapisuje do modele/
    python main.py prognoza --plik dane.csv [--obiekt X]   backtest na danych z pliku + prognoza na kolejne 24 h
    python main.py prognoza --obiekt RY_PZ1                bez pliku: dane z bazy, prognoza na 24 h po ostatniej godzinie

Plik CSV – format rozpoznawany automatycznie:
  1. licznik narastający   data;godzina;typ;wartosc;status        (jak pliki mock_* – przyrosty liczone jak w ETL)
  2. raport dystrybutora   jak Rap_godzinowy_*.csv                (znacznik = koniec godziny, cp1250)
  3. prosty                czas;kwh  [obiekt_id]                  (czas lokalny = początek godziny; --koniec-godziny)

Cechy liczy ta sama funkcja zbuduj() co w treningu i ocenie modelu. Historia: jeśli obiekt jest w bazie, wcześniejsze
godziny są dociągane z bazy (model potrzebuje ok. 5 tygodni wstecz). Pogoda: z bazy (ERA5 + prognozy z dnia
poprzedniego), a ostatnie dni i jutro – z bieżącej prognozy Open-Meteo.
"""
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import xgboost as xgb

from etl.config import POGODA_PUNKTY
from etl.wspolne import lokalny_na_utc, licznik_na_godziny, energia_koniec_godziny_na_utc
from .cechy import zbuduj, kolumny_grup
from .config import H, TZ, XGB, WYNIKI

MODELE = Path(os.environ.get("MODELE_DIR", Path(__file__).resolve().parents[1] / "modele"))
WARIANT = "xgb_prognoza_pogody"
GRUPY_MODELU = ["kalendarz", "lagi", "obiekt", "opad_przeszly", "pogoda_przeszla", "pogoda_prognoza"]
MIN_HISTORII_H = 24 * 35          # mediana z 28 dni + profil 4 tygodni + lagi
WALIDACJA = 0.10                  # końcówka każdego obiektu do ustalenia liczby drzew
PROSTE_REGULY = {"naiwny_doba": "wczoraj o tej godzinie", "naiwny_tydzien": "tydzień temu",
                 "profil_4tyg": "mediana z 4 tygodni"}            # punkty odniesienia w backteście
URL_BIEZACA = "https://api.open-meteo.com/v1/forecast"


# ============================================================ trening i zapis

def _gotowe_wiersze(f):
    return f[f["y_log"].notna() & f["poziom"].notna() & f["b_profil_4tyg"].notna()].copy()


def trenuj(d, zapisz=True):
    """1) early stopping na ostatnich 10% czasu każdego obiektu -> liczba drzew, 2) trening na WSZYSTKICH danych."""
    f = _gotowe_wiersze(zbuduj(d))
    X = kolumny_grup(GRUPY_MODELU)
    granica = f.groupby("obiekt_id")["czas"].transform(lambda t: t.quantile(1 - WALIDACJA))
    tr, wal = f[f["czas"] < granica], f[f["czas"] >= granica]
    m = xgb.XGBRegressor(**XGB).fit(tr[X], tr["y_log"], eval_set=[(wal[X], wal["y_log"])], verbose=False)
    drzew = m.best_iteration + 1
    pw = np.expm1(np.clip(m.predict(wal[X]), 0, None)) * wal["poziom"].values
    wape_wal = _wape_doba(wal.assign(prognoza=pw))

    parametry = {k: v for k, v in XGB.items() if k != "early_stopping_rounds"} | {"n_estimators": drzew}
    model = xgb.XGBRegressor(**parametry).fit(f[X], f["y_log"], verbose=False)
    meta = dict(wariant=WARIANT, grupy=GRUPY_MODELU, kolumny=X, horyzont_h=H, drzew=drzew,
                wape_doba_walidacja=round(wape_wal, 2), obiekty=sorted(f["obiekt_id"].unique()),
                dane_od=str(f["czas"].min()), dane_do=str(f["czas"].max()), godzin=int(len(f)),
                zakres={o: [str(g.min()), str(g.max())] for o, g in f.groupby("obiekt_id")["czas"]},
                wytrenowano=datetime.now().isoformat(timespec="seconds"))
    if zapisz:
        MODELE.mkdir(parents=True, exist_ok=True)
        model.save_model(MODELE / f"{WARIANT}.json")
        (MODELE / f"{WARIANT}_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return model, meta


def wczytaj_model():
    p = MODELE / f"{WARIANT}.json"
    if not p.exists():
        raise FileNotFoundError(f"Brak wytrenowanego modelu w {MODELE}. Uruchom: python main.py prognoza --trenuj")
    m = xgb.XGBRegressor()
    m.load_model(p)
    return m, json.loads((MODELE / f"{WARIANT}_meta.json").read_text(encoding="utf-8"))


# ============================================================ wczytanie pliku

def _rodzaj_pliku(sciezka, sep=None):
    with open(sciezka, "rb") as fh:
        pierwsza = fh.readline().decode("cp1250", errors="replace")
    if re.search(r"PPE|Rodzaj|Kompletno|Płatnik|P.atnik", pierwsza, re.I):
        return "raport"
    pola = pierwsza.strip().split(sep or ";")
    if len(pola) == 5 and re.match(r"\d{4}-\d{2}-\d{2}$", pola[0].strip()) and ":" in pola[1]:
        return "licznik"
    if len(pola) == 5 and pola[0].strip().lower() == "data" and pola[1].strip().lower() == "godzina":
        return "licznik"
    return "prosty"


def _kodowanie(sciezka, kodowanie=None):
    """Podane kodowanie albo wykrycie: UTF-8, a gdy plik nim nie jest - Windows-1250."""
    if kodowanie:
        return kodowanie
    try:
        with open(sciezka, encoding="utf-8-sig") as fh:
            fh.read(2_000_000)
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "cp1250"


def wczytaj_plik(sciezka, koniec_godziny=False, sep=None, kodowanie=None):
    """CSV -> (DataFrame obiekt_id?, czas UTC, kwh, rodzaj formatu). obiekt_id tylko gdy jest w pliku.
    sep / kodowanie: None = rozpoznanie automatyczne; podane - maja pierwszenstwo."""
    rodzaj = _rodzaj_pliku(sciezka, sep)
    if rodzaj == "raport":
        from etl.ry import wczytaj_raport
        e, _ = wczytaj_raport(sciezka, kodowanie or "cp1250")
        e = e.drop_duplicates("czas").sort_values("czas")
        s = energia_koniec_godziny_na_utc(e["czas"], e["kwh"])
        return pd.DataFrame({"czas": s.index, "kwh": s.mask(s == 0).values}), rodzaj
    if rodzaj == "licznik":
        kod = _kodowanie(sciezka, kodowanie)
        with open(sciezka, encoding=kod, errors="replace") as fh:
            header = None if fh.readline().lstrip("\ufeff")[:1].isdigit() else 0
        df = pd.read_csv(sciezka, sep=sep or ";", header=header, names=["data", "godzina", "typ", "wartosc", "status"],
                         encoding=kod, encoding_errors="replace").drop_duplicates()
        # „Wartość z pomiaru” – odporne na kodowanie (UTF-8 / Windows-1250 / krzaki w „ść”) i spacje na końcu
        df = df[df["status"].astype(str).str.strip().str.match(r"^Warto.{1,4} z pomiaru$")]
        df["czas"] = pd.to_datetime(df["data"].astype(str) + " " + df["godzina"].astype(str), errors="coerce")
        df = df.dropna(subset=["czas"])
        s = licznik_na_godziny(lokalny_na_utc(df["czas"]), pd.to_numeric(df["wartosc"], errors="coerce"))
        return pd.DataFrame({"czas": s.index, "kwh": s.values}), rodzaj
    df = pd.read_csv(sciezka, sep=sep, engine="python", encoding=_kodowanie(sciezka, kodowanie), encoding_errors="replace")
    return z_ramki(df, koniec_godziny), rodzaj


def wczytaj_pliki(sciezki, koniec_godziny=False, sep=None, kodowanie=None):
    """Kilka plikow tej samej pompowni (np. miesiace osobno) -> jedna seria; powtorzone godziny: ostatni plik wygrywa."""
    czesci, rodzaje = [], []
    for s in sciezki:
        df, r = wczytaj_plik(s, koniec_godziny, sep, kodowanie)
        czesci.append(df)
        rodzaje.append(r)
    nowe = pd.concat(czesci, ignore_index=True).sort_values("czas").drop_duplicates("czas", keep="last")
    return nowe.reset_index(drop=True), ", ".join(sorted(set(rodzaje)))


def z_ramki(df, koniec_godziny=False):
    """Prosty format z DataFrame (także z aplikacji): czas, kwh [, obiekt_id]. Czas lokalny bez strefy albo z strefą."""
    df = df.rename(columns=str.lower)
    if "czas" not in df or "kwh" not in df:
        raise ValueError("Plik musi mieć kolumny 'czas' i 'kwh' (albo format licznika / raportu dystrybutora).")
    kwh = pd.to_numeric(df["kwh"].astype(str).str.replace(",", ".").str.replace(" ", ""), errors="coerce")
    czas = pd.to_datetime(df["czas"], errors="coerce")
    ok = czas.notna()
    if getattr(czas.dt, "tz", None) is not None:
        utc = czas[ok].dt.tz_convert("UTC")
        if koniec_godziny:
            utc = utc - pd.Timedelta(hours=1)
        wynik = pd.DataFrame({"czas": utc.values, "kwh": kwh[ok].values})
    elif koniec_godziny:
        s = energia_koniec_godziny_na_utc(czas[ok].reset_index(drop=True), kwh[ok].reset_index(drop=True))
        wynik = pd.DataFrame({"czas": s.index, "kwh": s.values})
    else:
        wynik = pd.DataFrame({"czas": lokalny_na_utc(czas[ok].reset_index(drop=True)).values, "kwh": kwh[ok].values})
    if "obiekt_id" in df:
        wynik["obiekt_id"] = df.loc[ok, "obiekt_id"].astype(str).values
    wynik["czas"] = pd.to_datetime(wynik["czas"], utc=True)
    return wynik.dropna(subset=["czas"])


# ============================================================ pogoda bieżąca (ostatnie dni + jutro)

def pogoda_biezaca(stacja, dni_wstecz=10, dni_naprzod=3):
    """Open-Meteo Forecast: ostatnie dni (archiwum ERA5 ma kilka dni opóźnienia) i prognoza na jutro.
    Zwraca (pogoda, prognoza) w formatach tabel z bazy; bez internetu – puste ramki."""
    lat, lon = POGODA_PUNKTY[stacja]
    try:
        r = requests.get(URL_BIEZACA, params={"latitude": lat, "longitude": lon, "timezone": "GMT",
                                              "hourly": "temperature_2m,precipitation,rain,snowfall,snow_depth",
                                              "past_days": dni_wstecz, "forecast_days": dni_naprzod}, timeout=60)
        r.raise_for_status()
        h = pd.DataFrame(r.json()["hourly"])
    except Exception as e:
        print(f"  uwaga: brak bieżącej prognozy pogody ({type(e).__name__}) – cechy pogodowe ostatnich dni będą puste")
        return pd.DataFrame(), pd.DataFrame()
    h["czas"] = pd.to_datetime(h.pop("time")).dt.tz_localize("UTC")
    h = h.rename(columns={"temperature_2m": "temp_c", "precipitation": "opad_mm", "rain": "deszcz_mm",
                          "snowfall": "snieg_cm", "snow_depth": "pokrywa_m"})
    h.insert(0, "stacja", stacja)
    return h, h[["stacja", "czas", "opad_mm", "deszcz_mm", "snieg_cm", "temp_c"]].copy()


def _uzupelnij(baza, nowe):
    """Godziny z bazy mają pierwszeństwo, nowe uzupełniają braki (ostatnie dni i przyszłość)."""
    if nowe is None or nowe.empty:
        return baza
    k = ["stacja", "czas"]
    return pd.concat([baza, nowe[~nowe.set_index(k).index.isin(baza.set_index(k).index)]], ignore_index=True)


# ============================================================ prognoza

def dane_do_prognozy(d, oid, nowe=None, stacja=None, pobierz_pogode=True):
    """Słownik tabel dla jednego obiektu: historia z bazy + nowe dane z pliku + 24 h „przyszłości” do prognozy."""
    e = d["energia"][d["energia"]["obiekt_id"] == oid][["obiekt_id", "czas", "kwh"]]
    if nowe is not None and len(nowe):
        nowe = nowe.assign(obiekt_id=oid)[["obiekt_id", "czas", "kwh"]]
        e = pd.concat([e[~e["czas"].isin(nowe["czas"])], nowe], ignore_index=True)
    e = e.sort_values("czas").drop_duplicates("czas", keep="last")
    if e["kwh"].notna().sum() < MIN_HISTORII_H:
        raise ValueError(f"Za mało danych dla {oid}: {e['kwh'].notna().sum()} h, potrzeba co najmniej {MIN_HISTORII_H} h "
                         f"(~5 tygodni). Dołącz dłuższy plik albo obiekt z bazy.")
    ostatnia = e.loc[e["kwh"].notna(), "czas"].max()
    przyszlosc = pd.date_range(ostatnia + pd.Timedelta(hours=1), periods=H, freq="h")
    e = pd.concat([e, pd.DataFrame({"obiekt_id": oid, "czas": przyszlosc, "kwh": np.nan})], ignore_index=True)

    ob = d["obiekty"].set_index("obiekt_id")
    stacja = stacja or (ob.loc[oid, "stacja_pogody"] if oid in ob.index else "RY")
    obiekty = pd.DataFrame([dict(obiekt_id=oid, stacja_pogody=stacja,
                                 **{c: (ob.loc[oid, c] if oid in ob.index and c in ob else np.nan)
                                    for c in ["moc_pompy_kw", "wydajnosc_m3h", "zbiornik_m3"]})])
    pogoda, prognoza = d["pogoda"], d.get("prognoza", pd.DataFrame(columns=["stacja", "czas"]))
    if pobierz_pogode:
        pb, prb = pogoda_biezaca(stacja)
        pogoda, prognoza = _uzupelnij(pogoda, pb), _uzupelnij(prognoza, prb)
    puste = lambda kol: pd.DataFrame(columns=kol)
    return dict(energia=e, przeplyw=puste(["obiekt_id", "czas", "m3"]), scada=puste(["obiekt_id", "czas", "praca_pomp_h"]),
                opad_ru=d["opad_ru"] if oid.startswith("RU") else puste(["czas", "mm"]),
                pogoda=pogoda[pogoda["stacja"] == stacja], prognoza=prognoza[prognoza["stacja"] == stacja],
                kalendarz=d["kalendarz"], obiekty=obiekty), przyszlosc


def prognozuj(model, meta, dd, oid):
    """Prognoza kWh dla każdej godziny z wystarczającą historią (każda „dobę wcześniej”) + 24 h przyszłości."""
    f = zbuduj(dd)
    f = f[(f["obiekt_id"] == oid) & f["poziom"].notna()].copy()
    X = f.reindex(columns=meta["kolumny"])
    ob = [c for c in meta["kolumny"] if c.startswith("ob_")]
    X[ob] = X[ob].fillna(0.0)                                   # nowy obiekt = wszystkie ob_* równe 0 (jak transfer)
    f["prognoza"] = np.expm1(np.clip(model.predict(X), 0, None)) * f["poziom"].values
    f["czas_lokalny"] = f["czas"].dt.tz_convert(TZ)
    f = f.drop(columns=["profil_4tyg"]).rename(columns={"kwh": "rzeczywiste", "b_naiwny_doba": "naiwny_doba",
                          "b_naiwny_tydzien": "naiwny_tydzien",
                          "b_profil_4tyg": "profil_4tyg"})
    return f[["obiekt_id", "czas", "czas_lokalny", "rzeczywiste", "prognoza", *PROSTE_REGULY]]


def _wape_doba(df, kol="prognoza", rz="kwh"):
    d = df.assign(dzien=df["czas"].dt.tz_convert(TZ).dt.date).dropna(subset=[kol, rz])
    g = d.groupby(["obiekt_id", "dzien"])
    s = g[[rz, kol]].sum()[g[rz].count() >= 23]
    return float(100 * (s[kol] - s[rz]).abs().sum() / s[rz].sum()) if len(s) else np.nan


def ocena(wynik, od=None):
    """Backtest: godziny z rzeczywistym zużyciem (od początku pliku, jeśli podano). WAPE dobowe i godzinowe, bias."""
    b = wynik.dropna(subset=["rzeczywiste", "prognoza"])
    if od is not None:
        b = b[b["czas"] >= od]
    if b.empty:
        return {}, pd.DataFrame()
    b = b.rename(columns={"rzeczywiste": "kwh"})
    mies = b.assign(miesiac=b["czas_lokalny"].dt.tz_localize(None).dt.to_period("M").astype(str)) \
            .groupby("miesiac")[["kwh", "prognoza"]].sum()
    mies["roznica_proc"] = 100 * (mies["prognoza"] / mies["kwh"] - 1)
    porownanie = {"model": round(_wape_doba(b), 2),
                  **{k: round(_wape_doba(b, kol=k), 2) for k in PROSTE_REGULY if k in b and b[k].notna().any()}}
    return dict(godzin=int(len(b)), od=str(b["czas_lokalny"].min()), do=str(b["czas_lokalny"].max()),
                WAPE_doba=round(_wape_doba(b), 2), porownanie_WAPE_doba=porownanie,
                WAPE_h=round(float(100 * (b["prognoza"] - b["kwh"]).abs().sum() / b["kwh"].sum()), 2),
                bias_proc=round(float(100 * (b["prognoza"].sum() / b["kwh"].sum() - 1)), 2)), mies.round(1)


def wykres(wynik, oid, przyszlosc, sciezka, od=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    w = wynik if od is None else wynik[wynik["czas"] >= od - pd.Timedelta(days=7)]
    dz = w.assign(dzien=w["czas_lokalny"].dt.date).groupby("dzien")[["rzeczywiste", "prognoza"]].sum(min_count=20)
    fig, ax = plt.subplots(2, 1, figsize=(15, 8))
    ax[0].plot(dz.index, dz["rzeczywiste"], color="black", lw=1.3, label="rzeczywiste")
    ax[0].plot(dz.index, dz["prognoza"], lw=1.1, label="prognoza dobę wcześniej")
    ax[0].set_title(f"{oid} – kWh / dobę"); ax[0].legend(); ax[0].grid(alpha=0.3)
    o = wynik[wynik["czas"] >= przyszlosc[0] - pd.Timedelta(days=7)]
    ax[1].plot(o["czas_lokalny"], o["rzeczywiste"], color="black", lw=1.2, label="rzeczywiste")
    ax[1].plot(o["czas_lokalny"], o["prognoza"], lw=1.1, label="prognoza")
    ax[1].axvspan(przyszlosc[0].tz_convert(TZ), przyszlosc[-1].tz_convert(TZ), color="#1D9E75", alpha=0.12,
                  label="następne 24 h")
    ax[1].set_title(f"{oid} – ostatni tydzień i prognoza na 24 h [kWh/h]"); ax[1].legend(); ax[1].grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(sciezka, dpi=90); plt.close(fig)


def widziane_w_treningu(meta, oid, nowe):
    """Jaka część godzin z pliku mieści się w okresie, na którym model był trenowany (backtest byłby zawyżony)."""
    if nowe is None or not len(nowe) or oid not in meta.get("zakres", {}):
        return 0.0
    od, do = (pd.Timestamp(x) for x in meta["zakres"][oid])
    return float(nowe["czas"].between(od, do).mean())


def uruchom(oid, nowe=None, d=None, stacja=None, pobierz_pogode=True, katalog=None, uczciwie=False):
    """Całość dla jednego obiektu. Zwraca (wynik godzinowy, metryki backtestu, sumy miesięczne, prognoza 24 h).
    uczciwie=True: model trenowany na nowo BEZ godzin obiektu od początku pliku – prawdziwy test na nieznanych danych.
    Bez pliku (same dane z bazy) backtestu nie liczymy – model te godziny widział w treningu."""
    if d is None:
        from .dane import wczytaj
        d = wczytaj()
    if uczciwie and nowe is not None and len(nowe):
        e = d["energia"]
        model, meta = trenuj(dict(d, energia=e[~((e["obiekt_id"] == oid) & (e["czas"] >= nowe["czas"].min()))]), zapisz=False)
    else:
        model, meta = wczytaj_model()
    dd, przyszlosc = dane_do_prognozy(d, oid, nowe, stacja, pobierz_pogode)
    wynik = prognozuj(model, meta, dd, oid)
    # dane wejsciowe ostatniej prognozy (historia, pogoda, prognoza pogody, kalendarz) - dla zakladki „szczegoly”
    uruchom.ostatnie = dict(dd=dd, przyszlosc=przyszlosc, meta=meta, uczciwie=bool(uczciwie and nowe is not None),
                            z_pliku=int(len(nowe)) if nowe is not None else 0)
    od = nowe["czas"].min() if nowe is not None and len(nowe) else None
    met, mies = ocena(wynik, od) if od is not None else ({}, pd.DataFrame())
    if met:
        met["widziane_w_treningu_proc"] = round(100 * widziane_w_treningu(meta, oid, nowe), 1)
        met["uczciwie"] = bool(uczciwie)
    jutro = wynik[wynik["czas"].isin(przyszlosc)]
    katalog = Path(katalog or WYNIKI / "prognoza")
    katalog.mkdir(parents=True, exist_ok=True)
    wynik.assign(czas=wynik["czas"].astype(str), czas_lokalny=wynik["czas_lokalny"].astype(str)) \
         .drop(columns=[c for c in PROSTE_REGULY if c in wynik]).to_csv(katalog / f"{oid}_prognoza.csv", index=False)
    (katalog / f"{oid}_metryki.json").write_text(json.dumps(dict(obiekt=oid, model=meta["wariant"], backtest=met,
        jutro_kwh=round(float(jutro["prognoza"].sum()), 1), jutro_od=str(przyszlosc[0].tz_convert(TZ)),
        jutro_do=str(przyszlosc[-1].tz_convert(TZ))), indent=2, ensure_ascii=False), encoding="utf-8")
    wykres(wynik, oid, przyszlosc, katalog / f"{oid}_prognoza.png", od)
    return wynik, met, mies, jutro


def _obiekt_z_nazwy(sciezka):
    m = re.search(r"(PNB\d+|PZ\d+|ZMP|CH_T|RU_W|RU_ZMP)", Path(sciezka).stem, re.I)
    return {"PNB1": "RY_PNB1", "PZ1": "RY_PZ1", "ZMP": "RU_ZMP"}.get(m.group(1).upper(), m.group(1).upper()) if m \
        else re.sub(r"\W+", "_", Path(sciezka).stem)[:30]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python main.py prognoza")
    ap.add_argument("--trenuj", action="store_true", help="trenuj model na wszystkich danych z bazy i zapisz")
    ap.add_argument("--plik", help="CSV z danymi (licznik / raport dystrybutora / czas;kwh)")
    ap.add_argument("--obiekt", help="nazwa obiektu (domyślnie z nazwy pliku); obiekt z bazy = dociągnięta historia")
    ap.add_argument("--stacja", choices=list(POGODA_PUNKTY), help="punkt pogody (domyślnie z bazy, inaczej RY)")
    ap.add_argument("--koniec-godziny", action="store_true", help="format prosty: czas = koniec godziny")
    ap.add_argument("--bez-pogody-biezacej", action="store_true", help="nie pobieraj bieżącej prognozy z internetu")
    ap.add_argument("--uczciwie", action="store_true",
                    help="backtest na modelu trenowanym BEZ okresu z pliku (trening od nowa, ok. 1–2 min)")
    a = ap.parse_args(argv)

    if a.trenuj or not (MODELE / f"{WARIANT}.json").exists():
        from .dane import wczytaj
        print("== Trening modelu na wszystkich danych z bazy")
        _, meta = trenuj(wczytaj())
        print(f"  {meta['wariant']}: {meta['drzew']} drzew, {meta['godzin']:,} godzin, obiekty {', '.join(meta['obiekty'])}")
        print(f"  WAPE dobowe na walidacji (ostatnie 10% czasu obiektów): {meta['wape_doba_walidacja']}%")
        print(f"  zapisano: {MODELE / (WARIANT + '.json')}")
        if not (a.plik or a.obiekt):
            return
    if not (a.plik or a.obiekt):
        ap.error("podaj --plik albo --obiekt (albo --trenuj)")

    nowe, rodzaj = (None, "baza")
    if a.plik:
        nowe, rodzaj = wczytaj_plik(a.plik, a.koniec_godziny)
    oid = a.obiekt or (nowe["obiekt_id"].iloc[0] if nowe is not None and "obiekt_id" in nowe else _obiekt_z_nazwy(a.plik))
    print(f"== Prognoza: {oid} | źródło: {rodzaj}" + (f" ({len(nowe):,} h z pliku)" if nowe is not None else ""))
    wynik, met, mies, jutro = uruchom(oid, nowe, stacja=a.stacja, pobierz_pogode=not a.bez_pogody_biezacej,
                                      uczciwie=a.uczciwie)
    if nowe is None:
        print("\n  (bez pliku nie liczymy backtestu – model widział dane z bazy w treningu)")
    if met and met["widziane_w_treningu_proc"] > 0:
        print(f"\n  UWAGA: {met['widziane_w_treningu_proc']}% godzin z pliku model widział w treningu – backtest będzie "
              f"zawyżony. Prawdziwy test: dodaj --uczciwie.")
    if met:
        print(f"\n== Backtest{' UCZCIWY (model bez okresu z pliku)' if met['uczciwie'] else ''} (każda doba prognozowana "
              f"dzień wcześniej): {met['od'][:10]} → {met['do'][:10]}, {met['godzin']:,} h")
        print(f"  WAPE dobowe {met['WAPE_doba']}% | WAPE godzinowe {met['WAPE_h']}% | bias {met['bias_proc']:+}%")
        p = met["porownanie_WAPE_doba"]
        print("\n  porównanie na tych samych dobach (WAPE dobowe):")
        print(f"    model                    {p['model']:6.1f}%")
        for k, opis in PROSTE_REGULY.items():
            if k in p:
                print(f"    {opis:24s} {p[k]:6.1f}%   (model lepszy o {100 * (1 - p['model'] / p[k]):.0f}%)")
        print("\n  sumy miesięczne [kWh]:")
        print(mies.to_string())
    print(f"\n== Prognoza na następne 24 h: {jutro['czas_lokalny'].min():%Y-%m-%d %H:%M} → "
          f"{jutro['czas_lokalny'].max():%Y-%m-%d %H:%M} | razem {jutro['prognoza'].sum():.1f} kWh")
    print(jutro.assign(godzina=jutro["czas_lokalny"].dt.strftime("%d.%m %H:%M"))[["godzina", "prognoza"]]
          .round(2).to_string(index=False))
    print(f"\nWyniki: {WYNIKI / 'prognoza'}")


if __name__ == "__main__":
    main()
