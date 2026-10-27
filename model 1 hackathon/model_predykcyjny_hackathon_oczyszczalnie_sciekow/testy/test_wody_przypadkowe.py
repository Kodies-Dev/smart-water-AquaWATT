"""Wody przypadkowe: ranking pompowni i zdarzenia w formacie organizatorów (dzień, godziny, objętość) + eksport."""
import io
import sys

import pandas as pd
from openpyxl import load_workbook

from testy.conftest import ROOT

sys.path.insert(0, str(ROOT / "aplikacja"))


def test_ranking_i_zdarzenia(d):
    from backend_ml_llm import wody_przypadkowe as W
    dz = W.dobowo(d)
    r = W.ranking(dz)
    assert set(r["obiekt"]) == set(d["energia"]["obiekt_id"])
    assert r["infiltracja"].isin(["niska", "umiarkowana", "wysoka", "brak danych"]).all()
    z, szeregi = W.zdarzenia(d, dz)
    assert len(z) > 10
    assert {"dzien", "godziny", "czas_trwania_h", "objetosc_m3", "nadwyzka_kwh", "koszt_zl", "opad_mm", "typ"} <= set(z.columns)
    assert (z.groupby("zdarzenie")["czas_trwania_h"].sum() >= W.MIN_GODZIN).all() and (z["objetosc_m3"].dropna() >= 0).all()
    assert ((z["koszt_zl"] - z["nadwyzka_kwh"] * W.CENA_ZL_KWH).abs() <= 0.06).all()
    assert z["godziny"].str.match(r"^\d{2}:\d{2}–\d{2}:\d{2}").all()
    opad_zd = z.groupby("zdarzenie").agg(opad=("opad_mm", "sum"), typ=("typ", "first"))        # typ liczony dla zdarzenia
    assert (opad_zd.loc[opad_zd["typ"] == W.TYP_OPAD, "opad"] >= 1).all()
    assert z.groupby("zdarzenie")["typ"].nunique().max() == 1 and (z["dzien"] == z["poczatek"].dt.strftime("%Y-%m-%d")).all()
    wb = load_workbook(io.BytesIO(W.excel_zdarzen(z)))
    assert wb.sheetnames == ["Zdarzenia", "Podsumowanie", "Metoda"] and wb["Zdarzenia"].max_row == len(z) + 1


def test_komenda_zdarzenia(d, tmp_path, monkeypatch):
    import model.dane
    import model.config
    from backend_ml_llm import wody_przypadkowe as W
    monkeypatch.setattr(model.dane, "wczytaj", lambda *a, **k: d)
    monkeypatch.setattr(model.config, "WYNIKI", tmp_path)
    W.main(["--cena", "1.0"])
    assert (tmp_path / "zdarzenia_wod_przypadkowych.xlsx").exists() and (tmp_path / "zdarzenia_wod_przypadkowych.csv").exists()
    t = pd.read_csv(tmp_path / "zdarzenia_wod_przypadkowych.csv", sep=";", decimal=",")
    assert {"dzien", "godziny", "objetosc_m3"} <= set(t.columns) and len(t) > 10


def test_main_zdarzenia_przez_main_py(d, tmp_path, monkeypatch):
    """Komenda przez prawdziwe main.py (wcześniej błąd UnboundLocalError: Path)."""
    import main
    import model.dane
    import model.config
    monkeypatch.setattr(model.dane, "wczytaj", lambda *a, **k: d)
    monkeypatch.setattr(model.config, "WYNIKI", tmp_path)
    monkeypatch.setattr(sys, "argv", ["main.py", "zdarzenia"])
    main.main()
    assert (tmp_path / "zdarzenia_wod_przypadkowych.xlsx").exists()
