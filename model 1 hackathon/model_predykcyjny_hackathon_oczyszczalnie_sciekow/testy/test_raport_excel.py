"""Raport w Excelu z wykresami: arkusze, wykresy, formuły; Excel jako dane do prognozy."""
import io
import sys

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from testy.conftest import ROOT

sys.path.insert(0, str(ROOT / "aplikacja"))


def test_excel_jako_dane_do_prognozy(tmp_path):
    import model.prognoza as P
    lok = pd.date_range("2026-09-01", periods=24 * 40, freq="h")
    kwh = 10 + 5 * np.sin(np.arange(len(lok)) * 2 * np.pi / 24)
    warianty = {
        "czas_kwh": pd.DataFrame({"Czas": lok, "kWh": kwh}),
        "polskie": pd.DataFrame({"Data i godzina": lok.strftime("%Y-%m-%d %H:%M"), "Zużycie [kWh]": kwh}),
        "data_godzina": pd.DataFrame({"data": lok.date, "godzina": lok.strftime("%H:%M"), "energia": kwh}),
    }
    t = pd.date_range("2026-09-01", periods=24 * 40 * 4 + 1, freq="15min")
    licz = 500000 + np.concatenate([[0], np.cumsum(np.repeat(kwh / 4, 4))])
    warianty["licznik"] = pd.DataFrame({"data": t.strftime("%Y-%m-%d"), "godzina": t.strftime("%H:%M:%S"), "typ": "float (4)",
                                        "wartosc": licz.round(2), "status": "Wartość z pomiaru "})
    for nazwa, df in warianty.items():
        p = tmp_path / f"{nazwa}.xlsx"
        df.to_excel(p, index=False)
        nowe, rodzaj = P.wczytaj_plik(p)
        assert rodzaj.startswith("excel") and abs(nowe["kwh"].sum() - kwh.sum()) < 1, nazwa


def test_raport_excel_z_wykresami(d, tmp_path, monkeypatch):
    import model.prognoza as P
    import model.dlugi as D
    from backend_ml_llm.podsumowanie_klienta import podsumuj
    from backend_ml_llm.raport_excel import raport_excel
    monkeypatch.setattr(P, "MODELE", tmp_path)
    monkeypatch.setattr(P.requests, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError()))
    for k in (1, 2):
        P.trenuj(d, dni=k)
    D.trenuj(d)
    e = d["energia"][d["energia"]["obiekt_id"] == "RY_PZ1"]
    nowe = e[e["czas"] > e["czas"].max() - pd.Timedelta(weeks=6)][["czas", "kwh"]]
    w, met, mies, jutro, tydz, bl = P.uruchom_dni("RY_PZ1", nowe, d=d, pobierz_pogode=False, dni=7, katalog=tmp_path / "w")
    s, dz = podsumuj(("RY_PZ1", w, met, mies, jutro), {"zrodlo": "t.csv", "stacja": "RY"}, d)
    b = raport_excel("RY_PZ1", "t.csv", s, dz, jutro, mies, w, met, tydz, bl, {1: 13.9}, D.prognoza(d, "RY_PZ1", nowe),
                     None, "Raport.", "fakt")
    wb = load_workbook(io.BytesIO(b))
    assert wb.sheetnames == ["Podsumowanie", "Jutro godzinowo", "Dzień po dniu", "Miesięcznie", "Tydzień", "Plan 2 miesiące",
                             "Raport AI", "Godzinowo"]
    assert sum(len(ws._charts) for ws in wb.worksheets) >= 9
    wzory = [c.value for ws in wb.worksheets for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")]
    assert len(wzory) > 100 and not any(f in " ".join(wzory) for f in ("XLOOKUP", "FILTER(", "SORT(", "UNIQUE("))
    assert all("MAXIFS" not in f or "_xlfn.MAXIFS" in f for f in wzory)          # funkcje po 2007 z prefiksem
