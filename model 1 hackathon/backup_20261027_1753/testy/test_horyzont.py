"""Prognoza na kilka dni (modele na K dni naprzód) i plan na 2 miesiące (kwantyle, kalibracja przedziału)."""
import pandas as pd
from streamlit.testing.v1 import AppTest

from testy.test_aplikacja import APP, _plik_csv


def _bez_sieci(P, monkeypatch, tmp_path):
    monkeypatch.setattr(P, "MODELE", tmp_path)
    monkeypatch.setattr(P.requests, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("bez sieci")))


def test_prognoza_na_kilka_dni(d, tmp_path, monkeypatch):
    import model.prognoza as P
    from model.horyzont import ocen_dni
    _bez_sieci(P, monkeypatch, tmp_path)
    r1, r3 = [[x for x in ocen_dni(d, k) if x["obiekt"] == "RAZEM"][0] for k in (1, 3)]
    assert r1["model"] < r1["jak_k_dni_temu"] and r3["model"] < r3["jak_k_dni_temu"]   # model lepszy od „jak K dni temu”
    for k in (1, 2, 3):
        P.trenuj(d, dni=k)
    assert P.dostepne_dni() == 3
    e = d["energia"][d["energia"]["obiekt_id"] == "RY_PZ1"]
    nowe = e[e["czas"] > e["czas"].max() - pd.Timedelta(weeks=6)][["czas", "kwh"]]
    w, met, mies, jutro, tydz, bledy = P.uruchom_dni("RY_PZ1", nowe, d=d, pobierz_pogode=False, dni=7, katalog=tmp_path / "w")
    assert len(tydz) == 72 and sorted(tydz["dzien_naprzod"].unique()) == [1, 2, 3]       # ograniczone do wytrenowanych dni
    assert tydz["czas"].is_monotonic_increasing and tydz["prognoza"].notna().all()
    assert set(bledy) == {1, 2, 3} and all(0 < v < 50 for v in bledy.values())


def test_plan_na_2_miesiace(d, tmp_path, monkeypatch):
    import model.prognoza as P
    import model.dlugi as D
    _bez_sieci(P, monkeypatch, tmp_path)
    t, podsum = D.ocena(d)
    assert (t["model_p50"] < t["jak_ostatnie_4tyg"]).all()                              # lepiej niż „średnia z 4 tygodni”
    assert t["pokrycie_p10_p90"].between(70, 97).all()                                  # kalibracja: ok. 80% dni w przedziale
    _, meta = D.trenuj(d)
    assert meta["szerokosc_przedzialu"] >= 1.0
    dz, tyg, mies, start = D.prognoza(d, "RY_PZ1")
    assert len(dz) == 60 and (dz["dzien"].min() - start).days == 1
    assert ((dz["p10"] <= dz["p50"]) & (dz["p50"] <= dz["p90"])).all()
    assert abs(tyg["p50"].sum() - dz["p50"].sum()) < 1 and abs(mies["p50"].sum() - dz["p50"].sum()) < 1


def test_aplikacja_tydzien_i_plan(d, tmp_path, monkeypatch):
    import model.prognoza as P
    import model.dlugi as D
    _bez_sieci(P, monkeypatch, tmp_path)
    for k in (1, 2):
        P.trenuj(d, dni=k)
    D.trenuj(d)
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["d_baza"] = d
    at.session_state["zbiory"] = {"x": pd.DataFrame({"a": [1]})}
    at.session_state["aktywny"] = "x"
    at.run()
    at.file_uploader(key="pp_pliki").set_value([("RY_PZ1_test.csv", _plik_csv(d, "RY_PZ1"), "text/csv")]).run()
    [b for b in at.button if b.label == "Wczytaj pliki"][0].click().run()
    at.radio(key="tp_horyzont").set_value("Tydzień (7 dni)").run()
    at.checkbox(key="tp_uczciwie").uncheck().run()                                      # szybciej: bez treningu od nowa
    [b for b in at.button if b.label == "Przygotuj prognozę"][0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["prog_tydzien"][1]["dzien_naprzod"].max() == 2
    assert any(m.label.startswith("Razem 2 dni") for m in at.metric)
    at.radio(key="tp_horyzont").set_value("2 miesiące (plan)").run()
    [b for b in at.button if b.label == "Przygotuj plan na 2 miesiące"][0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.session_state["prog_plan"][1]) == 60
    assert any(m.label == "Najbliższe 4 tygodnie" for m in at.metric)
    assert any(b.label == "Plan w Excelu (z wykresami)" for b in at.get("download_button"))
