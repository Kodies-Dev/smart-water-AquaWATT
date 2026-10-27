"""Chorzów: liczniki energii i ścieków, alarmy."""
import pandas as pd

from .config import CH
from .wspolne import lokalny_na_utc, licznik_na_godziny, do_tabeli

READ = dict(encoding="utf-8-sig", encoding_errors="replace")
ALARMY = ["czas", "awaria_P1", "awaria_P2", "awaria_P3", "brak_transmisji", "awaria_zasuwy1",
          "awaria_zasuwy2", "awaria_sita", "spietrzenie", "praca_agregatu", "brak_wyd_P1",
          "brak_wyd_P2", "brak_wyd_P3", "wejscie_na_obiekt", "awaria_zasilania"]


def _licznik(plik, log):
    """Licznik CH: data;godzina;typ;wartosc;status (bez nagłówka) -> przyrost godzinowy."""
    path = CH / plik
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        header = None if f.readline()[:1].isdigit() else 0
    df = pd.read_csv(path, sep=";", header=header, names=["data", "godzina", "typ", "wartosc", "status"], **READ)
    n0 = len(df)
    df = df.drop_duplicates()
    df = df[df["status"].str.strip() == "Wartość z pomiaru"]
    df["czas"] = pd.to_datetime(df["data"] + " " + df["godzina"], errors="coerce")
    df = df.dropna(subset=["czas"])
    log(plik, "CH_T", n0, len(df), "status OK + bez duplikatów")
    return licznik_na_godziny(lokalny_na_utc(df["czas"]), df["wartosc"])


def energia(log, plik="zuzycie_energii.csv"):
    return do_tabeli(_licznik(plik, log), "CH_T", "kwh", zrodlo="licznik SCADA")


def przeplyw(log, plik="przepompowane_scieki.csv"):
    return do_tabeli(_licznik(plik, log), "CH_T", "m3")


def alarmy(log):
    """awarie_all -> format długi (czas, sygnal, stan). '-' i '*' pomijane."""
    df = pd.read_csv(CH / "awarie_all.csv", header=None, skiprows=1, names=ALARMY, dtype=str, **READ)
    df["czas"] = pd.to_datetime(df["czas"], format="%Y-%m-%d %H:%M.%S", errors="coerce")
    df = df.dropna(subset=["czas"]).reset_index(drop=True)
    df["czas"] = lokalny_na_utc(df["czas"]).values
    dl = df.melt(id_vars="czas", var_name="sygnal", value_name="stan")
    dl = dl[dl["stan"].isin(["0.00", "1.00"])].copy()
    dl["stan"] = (dl["stan"] == "1.00").astype(int)
    dl.insert(0, "obiekt_id", "CH_T")
    log("awarie_all.csv", "CH_T", len(df), len(dl), "format długi, bez '-' i '*'")
    return dl
