"""Model prognozy: brak podglądania przyszłości w cechach + model lepszy od naiwnego."""
import numpy as np
import pandas as pd

from model.cechy import zbuduj, kolumny_grup
from model.config import H


def test_cechy_nie_podgladaja_przyszlosci(d):
    """Zmiana zużycia PO chwili prognozy (t − H) nie może zmienić cech dla godziny t."""
    f1 = zbuduj(d)
    granica = pd.Timestamp("2025-03-01", tz="UTC")
    d2 = dict(d)
    e = d["energia"].copy()
    e.loc[e["czas"] > granica, "kwh"] *= 5                       # „przyszłość” zmieniona drastycznie
    d2["energia"] = e
    f2 = zbuduj(d2)
    cechy = kolumny_grup(["kalendarz", "lagi", "opad_przeszly", "pogoda_przeszla", "pogoda_prognoza"])
    t = granica + pd.Timedelta(hours=H)                          # prognoza dla t jest wydawana w chwili t − H = granica
    a = f1[f1["czas"] <= t].set_index(["obiekt_id", "czas"])[cechy]
    b = f2[f2["czas"] <= t].set_index(["obiekt_id", "czas"])[cechy]
    pd.testing.assert_frame_equal(a, b)


def test_xgboost_lepszy_od_naiwnego(d):
    from model.eksperymenty import main
    met = main(["--warianty", "naiwny_tydzien,profil_4tyg,xgb_kalendarz_lagi"], d=d)
    r = met[met["obiekt"] == "RAZEM"].set_index("wariant")["WAPE_doba"]
    assert r["xgb_kalendarz_lagi"] < r["naiwny_tydzien"]
    assert np.isfinite(r).all()


import pytest


@pytest.mark.parametrize("dni", [3, 7])
def test_cechy_nie_podgladaja_przyszlosci_dla_horyzontu(d, dni):
    """Prognoza na K dni naprzód: zmiana zużycia po chwili prognozy (t − 24·K) nie może zmienić cech dla godziny t."""
    h = 24 * dni
    granica = pd.Timestamp("2025-03-01", tz="UTC")
    d2 = dict(d)
    e = d["energia"].copy()
    e.loc[e["czas"] > granica, "kwh"] *= 5
    d2["energia"] = e
    f1, f2 = zbuduj(d, h=h), zbuduj(d2, h=h)
    cechy = kolumny_grup(["kalendarz", "lagi", "opad_przeszly", "pogoda_przeszla"])
    assert all(int(c[5:]) >= h for c in cechy if c.startswith("kwh_l"))          # same lagi >= horyzont
    t = granica + pd.Timedelta(hours=h)
    a = f1[f1["czas"] <= t].set_index(["obiekt_id", "czas"])[cechy]
    b = f2[f2["czas"] <= t].set_index(["obiekt_id", "czas"])[cechy]
    pd.testing.assert_frame_equal(a, b)
