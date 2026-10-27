"""Rybnik: liczniki przepływu, raporty godzinowe energii, faktury."""
import re

import pandas as pd

from .config import RY, ODETNIJ_PRZEPLYW_DO
from .wspolne import lokalny_na_utc, licznik_na_godziny, energia_koniec_godziny_na_utc, do_tabeli

READ = dict(encoding="utf-8-sig", encoding_errors="replace")
OBIEKT = {"PNB1": "RY_PNB1", "PZ1": "RY_PZ1"}


def przeplyw(log):
    wynik = []
    for kod, oid in OBIEKT.items():
        for f in sorted(RY.glob(f"{kod}_*.txt")):
            df = pd.read_csv(f, sep="\t", header=None, names=["tag", "czas", "wartosc", "status"],
                             na_values=["--"], **READ)
            n0 = len(df)
            df = df.drop_duplicates()
            df = df[df["status"].str.strip() == "Wartość z pomiaru"]
            df["czas"] = pd.to_datetime(df["czas"], errors="coerce")
            df = df.dropna(subset=["czas", "wartosc"])
            log(f.name, oid, n0, len(df), f"status OK; tagi: {df['tag'].unique().tolist()}")
            h = licznik_na_godziny(lokalny_na_utc(df["czas"]), df["wartosc"])
            if oid in ODETNIJ_PRZEPLYW_DO:
                h = h[h.index >= pd.Timestamp(ODETNIJ_PRZEPLYW_DO[oid], tz="UTC")]
            wynik.append(do_tabeli(h, oid, "m3"))
    return pd.concat(wynik, ignore_index=True)


def wczytaj_raport(f, kodowanie="cp1250"):
    """Jeden raport godzinowy dystrybutora (cp1250, ';', przecinek dziesiętny) -> wiersze energii czynnej pobranej
    z kompletnością >= 100%. Kolumna czas = KONIEC godziny, czas lokalny. Używane też przez tryb prognozy."""
    e = pd.read_csv(f, sep=";", decimal=",", encoding=kodowanie, encoding_errors="replace")
    e.columns = ["platnik", "ppe", "rodzaj", "czas", "strefa", "kwh", "kompl"]
    fmt = "%d.%m.%Y %H:%M" if "." in str(e["czas"].iloc[0]) else "%Y-%m-%d %H:%M"
    e["czas"] = pd.to_datetime(e["czas"], format=fmt, errors="coerce")
    n0 = len(e)
    e = e[e["rodzaj"].str.contains("czynna pobrana", na=False) & (e["kompl"] >= 100)]
    return e, n0


def energia(log):
    """Raporty godzinowe dystrybutora. Obiekt z nazwy pliku. Znacznik = koniec godziny."""
    czesci = {}
    for f in sorted(RY.glob("Rap_godzinowy*.csv")):
        m = re.search(r"-\s*(\w+)\s*$", f.stem)
        oid = OBIEKT.get(m.group(1)) if m else None
        if oid is None:
            log(f.name, None, 0, 0, "POMINIĘTY – nieznany obiekt w nazwie pliku")
            continue
        e, n0 = wczytaj_raport(f)
        log(f.name, oid, n0, len(e), f"PPE: {e['ppe'].unique().tolist()}")
        czesci.setdefault(oid, []).append(e)
    wynik = []
    for oid, lista in czesci.items():
        e = pd.concat(lista).drop_duplicates("czas", keep="first").sort_values("czas")
        s = energia_koniec_godziny_na_utc(e["czas"], e["kwh"])
        s = s.mask(s == 0)                      # 0 kWh = brak danych
        wynik.append(do_tabeli(s, oid, "kwh", zrodlo="raport dystrybutora"))
    return pd.concat(wynik, ignore_index=True)


def faktury(log):
    """Arkusz z blokami lat -> obiekt, miesiac, kwh. Rok z tytułu bloku."""
    rows = []
    for f in sorted(RY.glob("*faktur*.ods")):
        df = pd.read_excel(f, header=None, engine="odf")
        rok = None
        for _, r in df.iterrows():
            tekst = " ".join(str(x) for x in r.values if pd.notna(x))
            m = re.search(r"(\d{4})\s*ROK", tekst)
            if m:
                rok = int(m.group(1))
            kod = str(r[6]).replace(" ", "") if pd.notna(r[6]) else ""
            if rok and kod in OBIEKT:
                for i in range(12):
                    kwh = pd.to_numeric(r[8 + i], errors="coerce")
                    if pd.notna(kwh):
                        rows.append({"obiekt_id": OBIEKT[kod], "miesiac": pd.Timestamp(rok, i + 1, 1).date(),
                                     "kwh": float(kwh), "zrodlo": "faktura"})
        log(f.name, None, len(df), len(rows), "faktury miesięczne")
    return pd.DataFrame(rows)
