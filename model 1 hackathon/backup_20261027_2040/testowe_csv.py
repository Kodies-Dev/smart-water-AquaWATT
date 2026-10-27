"""Zestaw plików testowych do prognozy – wycinany z PRAWDZIWYCH danych w bazie (po python main.py etl).

    python testowe_csv.py        ->  Dane\\testowe\\*.csv  +  Dane\\testowe\\OPIS.md (co wybrać w aplikacji, czego się spodziewać)

Różne pompownie, pory roku, formaty (licznik jak mock_*, prosty czas;kwh, UTF-8 / Windows-1250) i przypadki
brzegowe (dziura w danych, reset licznika, za krótki plik). W aplikacji używaj ich w zakładce „Twoja prognoza”
– plik obejmuje okres z treningu, więc aplikacja sama włączy uczciwe sprawdzenie (model bez okresu z pliku).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

KATALOG = Path(__file__).resolve().parent
sys.path.insert(0, str(KATALOG))
TZ = "Europe/Warsaw"


def seria(d, oid, kol="kwh", tabela="energia"):
    df = d[tabela]
    return df[df["obiekt_id"] == oid].drop_duplicates("czas").set_index("czas")[kol].sort_index()


def okno(s, tygodnie, koniec=None):
    koniec = pd.Timestamp(koniec, tz="UTC") if koniec else s.index.max()
    return s[(s.index > koniec - pd.Timedelta(weeks=tygodnie)) & (s.index <= koniec)].dropna()


def zapisz_prosty(s, sciezka, kodowanie="utf-8"):
    pd.DataFrame({"czas": s.index.tz_convert(TZ).strftime("%Y-%m-%d %H:%M"), "kwh": s.round(3).values}) \
        .to_csv(sciezka, sep=";", index=False, encoding=kodowanie)


def zapisz_licznik(s, sciezka, kodowanie="utf-8", co_s=16, start=500000, reset_po=None, seed=0):
    """Licznik narastający dokładnie jak mock_*: data;godzina;float (4);wartość całkowita;Wartość z pomiaru (spacja na końcu).
    Odczyty co ~co_s sekund, czas lokalny. reset_po: po tylu godzinach licznik startuje od zera (wymiana licznika)."""
    rng = np.random.default_rng(seed)
    t = pd.date_range(s.index.min(), s.index.max() + pd.Timedelta(hours=1), freq=f"{co_s}s")
    t = t + pd.to_timedelta(rng.integers(0, co_s // 2, len(t)), unit="s")
    narast = np.concatenate([[0], s.cumsum().values])
    granice = np.concatenate([s.index.asi8, [(s.index[-1] + pd.Timedelta(hours=1)).value]])
    w = start + np.interp(t.asi8, granice, narast)
    if reset_po:
        moment = s.index[min(reset_po, len(s) - 1)].value
        w = np.where(t.asi8 >= moment, w - np.interp(moment, granice, narast) - start + 7, w)
    lok = t.tz_convert(TZ)
    linie = [f"{x:%Y-%m-%d};{x:%H:%M:%S};float (4);{int(v)};Wartość z pomiaru " for x, v in zip(lok, w)]
    sciezka.write_text("\n".join(linie) + "\n", encoding=kodowanie)


def main(d=None, katalog=None):
    if d is None:
        from model.dane import wczytaj
        d = wczytaj()
    out = Path(katalog or KATALOG / "Dane" / "testowe")
    out.mkdir(parents=True, exist_ok=True)
    jest = set(d["energia"]["obiekt_id"])
    opis = ["# Pliki testowe do prognozy\n",
            "Wycięte z prawdziwych danych. Używaj w zakładce **Twoja prognoza** (plik → pompownia → Przygotuj prognozę).",
            "Okresy są w danych treningowych, więc aplikacja sama włączy **uczciwe sprawdzenie** (model bez okresu z pliku,",
            "1–2 min) – to dokładnie scenariusz konkursu: model nie zna tych dni.\n",
            "| Plik | Pompownia w aplikacji | Co sprawdza | Czego się spodziewać |", "|---|---|---|---|"]

    def dodaj(nazwa, pompownia, co, wynik):
        opis.append(f"| `{nazwa}` | {pompownia} | {co} | {wynik} |")
        print(f"  {nazwa}")

    print(f"Zapisuję w {out}:")
    if "RY_PZ1" in jest:
        pz1 = seria(d, "RY_PZ1")
        s = okno(pz1, 8)
        zapisz_licznik(s, out / "01_PZ1_8tyg_licznik_mock.csv")
        dodaj("01_PZ1_8tyg_licznik_mock.csv", "RY_PZ1", "format jak mock_* (najbardziej prawdopodobny na konkursie)",
              "błąd dobowy kilka–kilkanaście %, prognoza 24 h")
        zapisz_prosty(s, out / "02_PZ1_8tyg_prosty.csv")
        dodaj("02_PZ1_8tyg_prosty.csv", "RY_PZ1", "te same 8 tygodni w formacie czas;kwh", "**prawie ten sam wynik co plik 01**")
        dz = s.drop(s.index[len(s) // 2: len(s) // 2 + 72])
        zapisz_prosty(dz, out / "03_PZ1_z_dziura_3doby.csv")
        dodaj("03_PZ1_z_dziura_3doby.csv", "RY_PZ1", "3 doby bez danych w środku pliku",
              "działa; brakujących dób nie ma w tabeli dzień po dniu")
        zapisz_licznik(s, out / "04_PZ1_licznik_z_resetem.csv", reset_po=len(s) // 3)
        dodaj("04_PZ1_licznik_z_resetem.csv", "RY_PZ1", "wymiana / reset licznika w trakcie pliku",
              "działa jak plik 01 (reset rozpoznany)")
        zapisz_prosty(okno(pz1, 3), out / "05_ZA_KROTKI_3tyg.csv")
        dodaj("05_ZA_KROTKI_3tyg.csv", "**nowa pompownia**, Rybnik", "za mało historii (3 tygodnie, obiekt spoza bazy)",
              "**komunikat „Za mało danych”** – tak ma być")
        zim = okno(pz1, 9, "2025-02-28")
        if len(zim) > 24 * 35:
            zapisz_prosty(zim, out / "06_PZ1_zima_2025_prosty.csv")
            dodaj("06_PZ1_zima_2025_prosty.csv", "RY_PZ1", "zima: śnieg, roztopy, ferie, święta", "błąd zwykle większy niż latem")
    if "RY_PNB1" in jest:
        pnb = seria(d, "RY_PNB1")
        pow_ = okno(pnb, 10, "2024-10-15")
        if len(pow_) > 24 * 35:
            zapisz_prosty(pow_, out / "07_PNB1_powodz_IX2024.csv")
            dodaj("07_PNB1_powodz_IX2024.csv", "RY_PNB1", "**powódź 13–16.09.2024** (najtrudniejszy okres w danych)",
                  "duże błędy w dniach powodzi – opis wskaże dzień z ulewą")
        zapisz_licznik(okno(pnb, 8), out / "08_NOWA_POMPOWNIA_cp1250.csv", kodowanie="cp1250")
        dodaj("08_NOWA_POMPOWNIA_cp1250.csv", "**nowa pompownia**, Rybnik", "obca nazwa + kodowanie Windows-1250",
              "działa (model przenosi się na nową pompownię)")
    if "CH_T" in jest:
        zapisz_licznik(okno(seria(d, "CH_T"), 10), out / "09_CH_T_10tyg_licznik_mock.csv")
        dodaj("09_CH_T_10tyg_licznik_mock.csv", "CH_T", "Chorzów: pompownia mocno reagująca na deszcz",
              "większy błąd niż PZ1 (ulewy), model wyraźnie lepszy od „jak wczoraj”")
    if "RU_W" in jest:
        ru = okno(seria(d, "RU_W"), 10, "2026-02-28")
        if len(ru) > 24 * 35:
            zapisz_prosty(ru, out / "10_RU_W_zima_2026_prosty.csv")
            dodaj("10_RU_W_zima_2026_prosty.csv", "RU_W", "Ruda: zima, wody opadowe i roztopy", "błąd kilkanaście–dwadzieścia kilka %")
    if "RU_ZMP" in jest:
        zapisz_prosty(okno(seria(d, "RU_ZMP"), 8), out / "11_RU_ZMP_8tyg_prosty.csv")
        dodaj("11_RU_ZMP_8tyg_prosty.csv", "RU_ZMP", "spokojna pompownia (słaba reakcja na deszcz)", "mały błąd (kilka %)")

    opis += ["", "Uwagi:",
             "- Plik raportu dystrybutora masz już w danych: `Dane\\RY\\Rap_godzinowy_2024-09-30_2025-09-30_423633 - PZ1.csv` (rok, RY_PZ1).",
             "- Pliki 01, 04, 08, 09 mają dokładnie format `mock_*`: `2026-10-12;23:58:03;float (4);587593;Wartość z pomiaru `.",
             "- Po wgraniu pliku sprawdź podpis: liczba godzin, okres, suma kWh i rozpoznany format."]
    (out / "OPIS.md").write_text("\n".join(opis) + "\n", encoding="utf-8")
    print(f"\nOpis plików (co wybrać w aplikacji, czego się spodziewać): {out / 'OPIS.md'}")


if __name__ == "__main__":
    main()
