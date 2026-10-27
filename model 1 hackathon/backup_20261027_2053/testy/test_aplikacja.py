"""Aplikacja Streamlit (na bazie Detektora Anomalii GUS): start, detekcja z bazy i z CSV, kolumny zgodne z GUS."""
import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from testy.conftest import ROOT  # noqa: E402

APP = str(ROOT / "aplikacja" / "app.py")
def _plik_csv(d, oid, tygodnie=6, od_konca=0):
    """Plik czas;kwh (czas lokalny) z danych syntetycznych - jak wgrany przez użytkownika."""
    e = d["energia"][d["energia"]["obiekt_id"] == oid]
    koniec = e["czas"].max() - pd.Timedelta(weeks=od_konca)
    w = e[(e["czas"] > koniec - pd.Timedelta(weeks=tygodnie)) & (e["czas"] <= koniec)]
    lok = w["czas"].dt.tz_convert("Europe/Warsaw").dt.strftime("%Y-%m-%d %H:%M")
    return pd.DataFrame({"czas": lok, "kwh": w["kwh"].round(3)}).to_csv(sep=";", index=False).encode("utf-8")


KOLUMNY_GUS = ["Anomaly_IF", "Anomaly_LOF", "Anomaly_SVM", "Anomaly_Votes", "Anomaly_Final", "Has_Outlier",
               "Nagla_Zmiana", "Odstaje_Od_Innych", "Rodzaj_Anomalii"]


def _uruchom_detekcje(at):
    [b for b in at.button if b.label == "Uruchom detekcje"][0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at.session_state["result_df"]


def test_start_bez_danych():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert any("Wgraj plik" in i.value for i in at.info)                      # ekran startowy jak w Detektorze GUS


def test_detekcja_z_bazy_i_raport(d, monkeypatch):
    monkeypatch.setenv("POKAZ_ANOMALIE", "1")                    # zakładki anomalii są schowane – włączamy na test
    import sys
    sys.path.insert(0, str(ROOT / "aplikacja"))
    from backend_ml_llm.nasz_detektor import nasz_detektor
    from backend_ml_llm.mistral_raport_generator import report_generator
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["d_baza"] = d
    at.session_state["alarmy"] = pd.DataFrame([dict(obiekt_id="CH_T", czas=pd.Timestamp("2025-02-03 08:00", tz="UTC"),
                                                    sygnal="spietrzenie", stan=1)])
    at.session_state["zbiory"] = {"baza_dobowo": nasz_detektor.dobowo_do_podgladu(d)}
    at.session_state["aktywny"] = "baza_dobowo"
    res = _uruchom_detekcje(at.run())
    assert all(c in res for c in KOLUMNY_GUS)
    assert 0 < res["Anomaly_Final"].sum() < len(res) * 0.15
    assert len(at.get("plotly_chart")) >= 4                       # wykresy zakładki Anomalie się narysowały
    fakty = report_generator.build_row_facts(res[res["Anomaly_Final"] == 1].head(3), at.session_state["num_cols"])
    assert "Wykryta przez" in fakty and "Opis z potoku anomalii" in fakty


def test_detekcja_z_csv_godzinowego(d, monkeypatch):
    monkeypatch.setenv("POKAZ_ANOMALIE", "1")
    e = d["energia"][d["energia"]["obiekt_id"] == "RU_W"].merge(d["przeplyw"], on=["obiekt_id", "czas"], how="left")
    p = d["pogoda"][d["pogoda"]["stacja"] == "RU"][["czas", "opad_mm", "temp_c"]]
    csv = e.merge(p, on="czas", how="left").assign(czas=lambda x: x["czas"].dt.strftime("%Y-%m-%d %H:%M"))
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["zbiory"] = {"ru_w": csv}
    at.session_state["aktywny"] = "ru_w"
    at.run()
    at.radio(key="zrodlo_anomalii").set_value("Aktywny zbior - CSV godzinowy").run()
    res = _uruchom_detekcje(at)
    assert set(res["obiekt_id"]) == {"RU_W"} and res["Anomaly_Final"].sum() > 0


def test_prognoza_szczegoly(d, tmp_path, monkeypatch):
    import model.prognoza as P
    monkeypatch.setattr(P, "MODELE", tmp_path)
    monkeypatch.setattr(P.requests, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("bez sieci")))
    P.trenuj(d)
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["d_baza"] = d
    at.session_state["zbiory"] = {"x": pd.DataFrame({"a": [1]})}
    at.session_state["aktywny"] = "x"
    at.run()
    assert any("Najpierw przygotuj prognozę" in i.value for i in at.info)          # szczegóły bez prognozy: wskazówka
    # dwa pliki tej samej pompowni (dwa okresy) -> jedna seria
    at.file_uploader(key="pp_pliki").set_value([("RU_W_cz1.csv", _plik_csv(d, "RU_W", 4, od_konca=4), "text/csv"),
                                                ("RU_W_cz2.csv", _plik_csv(d, "RU_W", 4), "text/csv")]).run()
    [b for b in at.button if b.label == "Wczytaj pliki"][0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    dp = at.session_state["dane_prognozy"]
    assert dp["oid"] == "RU_W" and "+ 1 inne" in dp["zrodlo"] and len(dp["nowe"]) == 24 * 7 * 8
    [b for b in at.button if b.label == "Przygotuj prognozę"][0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["prog_dd"] is not None
    assert any("Na podstawie czego powstała prognoza" in m.value for m in at.markdown)
    assert any("Historia zużycia energii" in m.value for m in at.markdown)
    at.radio(key="ps_widok").set_value("godzinowo").run()
    assert not at.exception, [e.value for e in at.exception]

def test_zakladki_wody_przypadkowe_glownym_tematem(d, monkeypatch):
    monkeypatch.delenv("POKAZ_ANOMALIE", raising=False)
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["d_baza"] = d
    at.session_state["zbiory"] = {"x": pd.DataFrame({"a": [1]})}
    at.session_state["aktywny"] = "x"
    at.run()
    assert not at.exception, [x.value for x in at.exception]
    etykiety = [t.label.strip() for t in at.tabs]
    assert etykiety == ["Dane", "Wykresy", "Wody przypadkowe", "Detekcja anomalii", "Anomalie", "Prognoza", "Prognoza – szczegoly",
                        "Model", "Raport", "Pytanie", "Dobre praktyki"]
    assert any(m.label == "Najwięcej wód przypadkowych" for m in at.metric)            # zakładka wód przypadkowych policzona
    assert len(at.session_state["wp_rank"]) == d["energia"]["obiekt_id"].nunique()
    at.selectbox(key="wp_obiekt").set_value("RU_W").run()
    assert not at.exception, [x.value for x in at.exception]
    assert any("Infiltracja" in m.value for m in at.markdown)
    assert any(b.label.startswith("Zdarzenia – wszystkie pompownie (Excel)") for b in at.get("download_button"))
    at.selectbox(key="wp_zd_wybor").set_value(1).run()                                  # wykres godzinowy zdarzenia
    assert not at.exception, [x.value for x in at.exception]
    at.number_input(key="wp_cena").set_value(0.8).run()                                 # inna cena energii
    assert not at.exception, [x.value for x in at.exception]
    monkeypatch.setenv("POKAZ_ANOMALIE", "0")                                         # przełącznik nadal chowa anomalie
    at2 = AppTest.from_file(APP, default_timeout=180)
    at2.session_state["zbiory"] = {"x": pd.DataFrame({"a": [1]})}
    at2.session_state["aktywny"] = "x"
    at2.run()
    assert not any("Anomalie" in t.label or "Detekcja" in t.label for t in at2.tabs)

def test_wyniki_modeli_i_raport_o_prognozie(d, tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / "aplikacja"))
    import model.prognoza as P
    from model.eksperymenty import main as eksperymenty
    from backend_ml_llm.mistral_raport_generator import report_generator
    from backend_ml_llm.raport_prognozy import fakty, wczytaj_wyniki
    monkeypatch.setattr(P, "MODELE", tmp_path)
    monkeypatch.setattr(P.requests, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("bez sieci")))
    eksperymenty(["--warianty", "naiwny_doba,naiwny_tydzien,profil_4tyg,xgb_prognoza_pogody"], d=d)
    P.trenuj(d)
    prompty = []
    monkeypatch.setattr(report_generator, "ask_mistral", lambda prompt, model="x", timeout=0: prompty.append(prompt) or "RAPORT OK")

    meta, met, prog, waz = wczytaj_wyniki()
    f = fakty(meta, met, None)
    assert "WAPE dobowe modelu glownego" in f and "mniejszy blad" in f and "Per pompownia" in f

    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["d_baza"] = d
    at.session_state["zbiory"] = {"x": pd.DataFrame({"a": [1]})}
    at.session_state["aktywny"] = "x"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("WAPE dobowe" in m.label for m in at.metric)                  # Wyniki modeli: kafelki z wynikami
    assert len(at.get("plotly_chart")) >= 4
    [b for b in at.button if b.label == "Generuj raport"][0].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["raport_prognozy"] == "RAPORT OK"
    assert "NIE zmieniaj zadnych liczb" in prompty[-1] and "FAKTY" in prompty[-1]


def test_widok_klienta_twoja_prognoza(d, tmp_path, monkeypatch):
    import io
    import sys
    sys.path.insert(0, str(ROOT / "aplikacja"))
    import model.prognoza as P
    from backend_ml_llm.podsumowanie_klienta import podsumuj
    from backend_ml_llm.raport_excel import raport_excel
    from openpyxl import load_workbook
    monkeypatch.setattr(P, "MODELE", tmp_path)
    monkeypatch.setattr(P.requests, "get", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("bez sieci")))
    P.trenuj(d)

    # 1. podsumowanie z backtestem (plik = ostatnie 6 tygodni PZ1, uczciwie) + Excel
    e = d["energia"][d["energia"]["obiekt_id"] == "RY_PZ1"]
    nowe = e[e["czas"] > e["czas"].max() - pd.Timedelta(weeks=6)][["czas", "kwh"]]
    prog = ("RY_PZ1",) + P.uruchom("RY_PZ1", nowe, d=d, pobierz_pogode=False, uczciwie=True, katalog=tmp_path / "w")
    s, dz = podsumuj(prog, dict(zrodlo="test.csv", stacja="RY"), d)
    assert s["dni"] >= 40 and 0 < s["wape"] < 50 and "Średnio myliliśmy się" in s["tekst"] and "kWh" in s["tekst"]
    wb = load_workbook(io.BytesIO(raport_excel("RY_PZ1", "test.csv", s, dz, prog[4], prog[3], prog[1], prog[2])))
    assert {"Podsumowanie", "Jutro godzinowo", "Dzień po dniu", "Miesięcznie", "Godzinowo"} <= set(wb.sheetnames)
    assert wb["Jutro godzinowo"].max_row == 3 + 24                                       # nagłówek + 24 godziny
    assert len(wb["Dzień po dniu"]._charts) == 2 and len(wb["Podsumowanie"]._charts) == 1
    assert str(wb["Podsumowanie"]["B5"].value).startswith("=SUM(")                    # sumy jako formuły Excela

    # 2. aplikacja: dane wybrane w panelu bocznym -> zakładka Dane -> Prognoza (jeden przycisk)
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["d_baza"] = d
    at.session_state["zbiory"] = {"x": pd.DataFrame({"a": [1]})}
    at.session_state["aktywny"] = "x"
    at.run()
    assert not at.exception, [x.value for x in at.exception]
    assert any("Wgraj plik" in i.value for i in at.info)                     # bez danych: wskazówka
    at.file_uploader(key="pp_pliki").set_value([("RY_PZ1_test.csv", _plik_csv(d, "RY_PZ1"), "text/csv")]).run()
    [b for b in at.button if b.label == "Wczytaj pliki"][0].click().run()     # jak w Detektorze GUS
    assert not at.exception, [x.value for x in at.exception]
    assert at.selectbox(key="pp_obiekt").value == "RY_PZ1"                   # pompownia wykryta z nazwy pliku
    assert at.session_state["aktywny"] == "RY_PZ1_test"                      # wczytany plik = zbiór aktywny (Dane, Wykresy)
    assert any(s.label == "Zbior aktywny" for s in at.selectbox)
    assert any(m.label == "Średnio na dobę" for m in at.metric)              # podsumowanie danych w zakładce Prognoza
    assert all(not m.proto.delta for m in at.tabs[0].metric)                 # kafelki w zakładce Dane bez strzałek
    [b for b in at.button if b.label == "Przygotuj prognozę"][0].click().run()
    assert not at.exception, [x.value for x in at.exception]
    assert at.session_state["prog_wynik"][0] == "RY_PZ1"
    assert any(m.label.startswith("Prognoza na") for m in at.metric)
    assert any("przewidujemy" in m.value for m in at.markdown)               # opis prostym językiem
    assert len(at.get("download_button")) >= 2                               # Excel + CSV
