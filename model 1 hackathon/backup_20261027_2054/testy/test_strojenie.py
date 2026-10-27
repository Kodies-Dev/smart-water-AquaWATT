"""Strojenie (Optuna): walidacja krocząca tylko w części treningowej, zapis parametrów, użycie przy treningu."""
import json


def test_strojenie_i_uzycie_parametrow(d, tmp_path, monkeypatch):
    import model.prognoza as P
    from model.strojenie import main, okresy, parametry_modelu
    from model.cechy import zbuduj, podziel
    from model.config import PODZIAL, WALIDACJA
    f = podziel(zbuduj(d), PODZIAL, WALIDACJA)
    tr = f[f["zbior"] != "test"]
    test_od = f[f["zbior"] == "test"].groupby("obiekt_id")["czas"].min()
    for ucz, wal in okresy(tr):                                  # walidacja krocząca nie dotyka testu
        assert (wal.groupby("obiekt_id")["czas"].max() < test_od.reindex(wal["obiekt_id"].unique())).all()
        assert (ucz.groupby("obiekt_id")["czas"].max() <= wal.groupby("obiekt_id")["czas"].min()).all()
    w = main(["--proby", "2", "--minuty", "2"], d=d, katalog=tmp_path)
    assert (tmp_path / "parametry_optuna.json").exists() and w["prob"] >= 1
    assert set(json.loads((tmp_path / "parametry_optuna.json").read_text())) >= {"parametry", "uzyj", "test_domyslne"}
    p, zrodlo = parametry_modelu(tmp_path)
    assert zrodlo == ("optuna" if w["uzyj"] else "domyślne") and "learning_rate" in p
    monkeypatch.setattr(P, "MODELE", tmp_path)
    _, meta = P.trenuj(d)
    assert meta["parametry"] == zrodlo
