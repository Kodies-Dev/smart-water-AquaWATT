"""Ruda Śląska: energia godzinowa, opad, SCADA (W i ZMP)."""
import numpy as np
import pandas as pd

from .config import RU
from .wspolne import lokalny_na_utc, licznik_na_godziny, energia_koniec_godziny_na_utc, do_tabeli

READ = dict(encoding="utf-8-sig", encoding_errors="replace")
OBIEKT = {"W": "RU_W", "ZMP": "RU_ZMP"}
SCADA = {1: "czas", 2: "poziom", 3: "q", 4: "i1", 5: "i2", 6: "licznik", 12: "prog_alarm", 13: "prog_start", 14: "prog_stop"}
MIN_PROBEK = 60  # ~180 próbek/h przy kroku 20 s; mniej = godzina niepewna


def energia(log):
    wynik = []
    for kod, oid in OBIEKT.items():
        f = RU / f"energia_24-26-{kod}.csv"
        e = pd.read_csv(f, sep=";", decimal=",", **READ)
        e["Data_godzina"] = pd.to_datetime(e["Data_godzina"], errors="coerce")
        n0 = len(e)
        e = e.dropna(subset=["Data_godzina"])          # puste daty = wiosenna zmiana czasu
        log(f.name, oid, n0, len(e), "bez pustych dat")
        s = energia_koniec_godziny_na_utc(e["Data_godzina"], e["Wartosc_kWh"])
        s = s.mask(s == 0)
        wynik.append(do_tabeli(s, oid, "kwh", zrodlo="licznik energii"))
    return pd.concat(wynik, ignore_index=True)


def opad(log):
    """Intensywność [mm/h] co 1 min (zapis tylko przy opadzie), UTC -> mm na godzinę. Brak wpisu = 0 mm."""
    df = pd.read_csv(RU / "intensywnosc_opadu.csv", sep=";", decimal=",", **READ)
    df.columns = ["czas", "mmh"]
    df["czas"] = pd.to_datetime(df["czas"], errors="coerce").dt.tz_localize("UTC")
    df = df.dropna()
    s = (df.set_index("czas")["mmh"] / 60).resample("1h").sum()
    log("intensywnosc_opadu.csv", None, len(df), len(df),
        f"{len(df):,} wpisów minutowych → {len(s):,} godzin, suma {s.sum():.0f} mm")
    return s.rename("mm").rename_axis("czas").reset_index().assign(stacja="RU")[["stacja", "czas", "mm"]]


def scada(log):
    """SCADA W i ZMP -> agregaty godzinowe + przepływ z licznika (tylko W)."""
    scada_out, przeplyw_out = [], []
    for kod, oid in {"w": "RU_W", "ZMP": "RU_ZMP"}.items():
        godz, licz = [], []
        for f in sorted(RU.glob(f"SCADA_{kod}_*.csv")):
            if "_part" in f.stem:
                continue
            df = pd.read_csv(f, sep=";", decimal=",", header=None, usecols=list(SCADA), **READ)
            df.columns = [SCADA[c] for c in df.columns]
            n0 = len(df)
            df["czas"] = pd.to_datetime(df["czas"], errors="coerce")
            df = df[(df["prog_alarm"] > 0) & df["czas"].notna()].reset_index(drop=True)
            df["czas"] = lokalny_na_utc(df["czas"]).values
            log(f.name, oid, n0, len(df), "bez wierszy-przerw (progi = 0)")
            s = df.set_index("czas")
            h = s.resample("1h")
            g = pd.DataFrame({
                "poziom_sr": h["poziom"].mean(),
                "poziom_max": h["poziom"].max(),
                "przeplyw_chw_sr": s["q"].clip(lower=0).resample("1h").mean() if oid == "RU_W" else np.nan,
                "prad_p1_sr": h["i1"].mean(),
                "prad_p2_sr": h["i2"].mean(),
                "praca_pomp_h": ((s["i1"] > 1).astype(float) + (s["i2"] > 1).astype(float)).resample("1h").mean(),
                "prog_start": h["prog_start"].median(),
                "prog_stop": h["prog_stop"].median(),
                "liczba_probek": h["poziom"].count(),
            })
            malo = g["liczba_probek"] < MIN_PROBEK
            g.loc[malo, g.columns.drop("liczba_probek")] = np.nan
            godz.append(g)
            if oid == "RU_W":
                licz.append(df[["czas", "licznik"]])
        g = pd.concat(godz)
        g = g[~g.index.duplicated(keep="first")].rename_axis("czas").reset_index()
        g.insert(0, "obiekt_id", oid)
        scada_out.append(g[g["liczba_probek"] > 0])
        if licz:
            l = pd.concat(licz)
            przeplyw_out.append(do_tabeli(licznik_na_godziny(l["czas"], l["licznik"]), oid, "m3"))
    return pd.concat(scada_out, ignore_index=True), pd.concat(przeplyw_out, ignore_index=True)
