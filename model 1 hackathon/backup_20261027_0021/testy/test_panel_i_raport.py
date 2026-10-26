"""Tryb panelowy (na wzór Detektora Anomalii GUS) i raport słowny."""
import numpy as np
import pandas as pd

from anomalie.panel import dodaj_cechy_panelowe, dodaj_rodzaj


def _panel(n_dni=120, seed=0):
    rng = np.random.default_rng(seed)
    dni = pd.date_range("2025-01-01", periods=n_dni, freq="D")
    wspolny = rng.normal(0, 10, n_dni)                                   # wspólna „pogoda” wszystkich pompowni
    rows = []
    for oid in ["A", "B", "C", "D"]:
        v = wspolny + rng.normal(0, 3, n_dni)
        if oid == "A":
            v[100:105] += 60                                             # tylko A ma nadwyżkę – reszta nie
        rows.append(pd.DataFrame({"obiekt_id": oid, "dzien": dni, "residual_proc": v}))
    return pd.concat(rows, ignore_index=True)


def test_odstaje_od_innych_dziala_przy_malej_liczbie_obiektow():
    df = dodaj_cechy_panelowe(_panel(), kolumny=["residual_proc"])
    a = df[df["obiekt_id"] == "A"].set_index("dzien")["residual_proc_zscore_miedzy"]
    assert a.iloc[100:105].min() > 5                                     # klasyczny z-score przy 4 obiektach dałby max 1,5
    assert a.iloc[:95].abs().median() < 1.5
    b = df[df["obiekt_id"] == "B"].set_index("dzien")["residual_proc_zscore_miedzy"]
    assert b.iloc[100:105].abs().max() < 3                               # inne obiekty w tym czasie – bez fałszywego alarmu


def test_nagla_zmiana_i_rodzaj():
    df = dodaj_cechy_panelowe(_panel(), kolumny=["residual_proc"])
    df["anomalia"] = (df["obiekt_id"] == "A") & df["dzien"].between("2025-04-11", "2025-04-15")
    df = dodaj_rodzaj(df, kolumny=["residual_proc"])
    r = df[df["anomalia"]]["Rodzaj_Anomalii"]
    assert r.str.contains("odstaje od innych").all()
    assert r.iloc[0] == "nagła zmiana + odstaje od innych"               # pierwszy dzień skoku: oba wzorce
    assert df.loc[~df["anomalia"], "Rodzaj_Anomalii"].isna().all()


def test_raport_bez_ollamy_i_z_ollama(tmp_path, monkeypatch):
    import anomalie.raport as rap
    monkeypatch.setattr(rap, "WYNIKI", tmp_path)
    dni = pd.DataFrame({"obiekt_id": ["CH_T", "CH_T"], "dzien": ["2025-06-10", "2025-06-11"], "glosy": [3, 0],
                        "anomalia": [True, False], "typ": ["spadek – awaria / przerwa", None],
                        "skala_m3": [-400.0, None], "skala_kwh": [-70.0, None],
                        "opis": ["CH_T 2025-06-10: spadek – awaria / przerwa; ...", None]})
    dni.to_csv(tmp_path / "dni.csv", index=False)
    pd.DataFrame({"obiekt": ["CH_T"], "anomalii": [1], "udzial_wod_obcych_proc": [9.2]}).to_csv(tmp_path / "ranking.csv", index=False)

    def brak(*a, **k):
        raise ConnectionError("brak Ollamy")
    monkeypatch.setattr(rap.requests, "post", brak)
    md, zrodlo = rap.raport()
    assert "bez modelu językowego" in zrodlo and "spadek – awaria / przerwa" in md and (tmp_path / "raport.md").exists()

    class Odp:
        def raise_for_status(self): pass
        def json(self): return {"response": "<think>liczę...</think>W Chorzowie wystąpiła jedna anomalia."}
    monkeypatch.setattr(rap.requests, "post", lambda *a, **k: Odp())
    md, zrodlo = rap.raport(model="qwen3:8b")
    assert "Ollama" in zrodlo and "W Chorzowie" in md and "<think>" not in md
    assert "Fakty źródłowe" in md                                        # liczby zawsze dołączone wprost
