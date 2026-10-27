"""Strojenie hiperparametrów XGBoost – Optuna z walidacją kroczącą (rolling-origin / time-series CV).

    python main.py strojenie [--proby 30] [--minuty 20]

Metodologia (żeby wynik na teście był czysty):
  1. Strojenie TYLKO na części treningowej (pierwsze 70% czasu każdej pompowni).
  2. Walidacja krocząca: 3 okresy – model uczony na danych do punktu podziału (55 / 70 / 85% części treningowej),
     oceniany na kolejnych 15% → wynik = średni WAPE dobowy z 3 okresów.
  3. Test (ostatnie 30%) otwierany RAZ, na końcu: parametry domyślne vs dostrojone, ta sama procedura co w eksperymentach.
  4. Dostrojone parametry trafiają do modele/parametry_optuna.json; trening modelu do pracy używa ich tylko wtedy,
     gdy są lepsze na teście (pole "uzyj").
"""
import argparse
import json
import time

import numpy as np
import pandas as pd
import xgboost as xgb

from .cechy import zbuduj, podziel, kolumny_grup
from .config import PODZIAL, WALIDACJA, XGB, TZ

GRUPY = ["kalendarz", "lagi", "obiekt", "opad_przeszly", "pogoda_przeszla", "pogoda_prognoza"]   # model główny
PUNKTY = [0.55, 0.70, 0.85]          # punkty podziału części treningowej (per pompownia)
OKNO = 0.15                          # długość okresu walidacyjnego (ułamek części treningowej)
MIN_ZYSK = 0.1                       # [pp WAPE] – mniejsza poprawa na teście to szum, zostają parametry domyślne
STALE = {k: v for k, v in XGB.items() if k not in ("n_estimators", "early_stopping_rounds", "learning_rate", "max_depth",
                                                    "min_child_weight", "subsample", "colsample_bytree")}


def _wape_doba(df, pred):
    d = df[["obiekt_id", "czas", "kwh"]].assign(p=pred, dzien=df["czas"].dt.tz_convert(TZ).dt.date)
    g = d.groupby(["obiekt_id", "dzien"])
    s = g[["kwh", "p"]].sum()[g["kwh"].count() >= 23]
    return float(100 * (s["p"] - s["kwh"]).abs().sum() / s["kwh"].sum())


def _fit(params, tr, wal, X):
    m = xgb.XGBRegressor(**params, n_estimators=4000, early_stopping_rounds=100)
    m.fit(tr[X], tr["y_log"], eval_set=[(wal[X], wal["y_log"])], verbose=False)
    return m


def _kwh(m, df, X):
    return np.expm1(np.clip(m.predict(df[X]), 0, None)) * df["poziom"].values


def okresy(tr):
    """Walidacja krocząca w części treningowej: (ucz, waliduj) dla każdego punktu podziału, osobno per pompownia."""
    for q in PUNKTY:
        t0 = tr.groupby("obiekt_id")["czas"].transform(lambda t: t.quantile(q))
        t1 = tr.groupby("obiekt_id")["czas"].transform(lambda t: t.quantile(min(q + OKNO, 1.0)))
        yield tr[tr["czas"] < t0], tr[(tr["czas"] >= t0) & (tr["czas"] <= t1)]


def ocena_cv(params, tr, X):
    wyniki, drzewa = [], []
    for ucz, wal in okresy(tr):
        m = _fit(params, ucz, wal, X)
        wyniki.append(_wape_doba(wal, _kwh(m, wal, X)))
        drzewa.append(m.best_iteration + 1)
    return float(np.mean(wyniki)), wyniki, drzewa


def test_raz(params, f, X):
    """Jak w eksperymentach: uczenie na treningu, early stopping na walidacji, ocena na teście."""
    tr, wal, te = (f[f["zbior"] == z] for z in ("trening", "walidacja", "test"))
    m = _fit(params, tr, wal, X)
    return _wape_doba(te, _kwh(m, te, X)), m.best_iteration + 1


def domyslne():
    return {k: XGB[k] for k in ("learning_rate", "max_depth", "min_child_weight", "subsample", "colsample_bytree")} | STALE


def main(argv=None, d=None, katalog=None):
    import optuna
    ap = argparse.ArgumentParser(prog="python main.py strojenie")
    ap.add_argument("--proby", type=int, default=30, help="liczba prób Optuny")
    ap.add_argument("--minuty", type=float, default=20, help="limit czasu strojenia")
    a = ap.parse_args(argv)
    from .prognoza import MODELE
    katalog = katalog or MODELE

    if d is None:
        from .dane import wczytaj
        d = wczytaj()
    f = podziel(zbuduj(d), PODZIAL, WALIDACJA)
    X = kolumny_grup(GRUPY)
    tr = f[f["zbior"] != "test"]
    print(f"== Strojenie: {len(tr):,} godzin w części treningowej, walidacja krocząca: {len(PUNKTY)} okresy".replace(",", " "))

    t = time.time()
    baza, okr, drz = ocena_cv(domyslne(), tr, X)
    print(f"  parametry domyślne: CV {baza:.2f}% (okresy {', '.join(f'{w:.1f}' for w in okr)}; drzewa {drz}) – {time.time() - t:.0f} s")

    def cel(trial):
        p = STALE | dict(
            learning_rate=trial.suggest_float("learning_rate", 0.015, 0.15, log=True),
            max_depth=trial.suggest_int("max_depth", 3, 10),
            min_child_weight=trial.suggest_float("min_child_weight", 1, 60, log=True),
            subsample=trial.suggest_float("subsample", 0.5, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.3, 1.0),
            reg_lambda=trial.suggest_float("reg_lambda", 1e-3, 20, log=True),
            reg_alpha=trial.suggest_float("reg_alpha", 1e-3, 5, log=True),
        )
        wynik, _, _ = ocena_cv(p, tr, X)
        print(f"  próba {trial.number + 1:2d}: CV {wynik:.2f}%")
        return wynik

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=42))
    study.enqueue_trial({k: v for k, v in domyslne().items() if k in ("learning_rate", "max_depth", "min_child_weight",
                                                                     "subsample", "colsample_bytree")}
                        | {"reg_lambda": 1.0, "reg_alpha": 0.001})
    study.optimize(cel, n_trials=a.proby, timeout=a.minuty * 60)
    najlepsze = STALE | study.best_params
    print(f"\n  najlepsza próba: CV {study.best_value:.2f}% (domyślne {baza:.2f}%) po {len(study.trials)} próbach, "
          f"{(time.time() - t) / 60:.1f} min")

    print("\n== Test (otwierany raz, ostatnie 30% czasu każdej pompowni)")
    test_dom, drz_dom = test_raz(domyslne(), f, X)
    test_naj, drz_naj = test_raz(najlepsze, f, X)
    print(f"  domyślne:  WAPE dobowe {test_dom:.2f}%  ({drz_dom} drzew)")
    print(f"  dostrojone: WAPE dobowe {test_naj:.2f}%  ({drz_naj} drzew)")
    uzyj = test_naj <= test_dom - MIN_ZYSK
    print(f"  → {'dostrojone LEPSZE – model do pracy będzie ich używał' if uzyj else f'zysk < {MIN_ZYSK} pp na teście – zostają domyślne'}")

    katalog.mkdir(parents=True, exist_ok=True)
    wynik = dict(parametry=najlepsze, uzyj=bool(uzyj), cv_domyslne=round(baza, 3), cv_najlepsze=round(study.best_value, 3),
                 test_domyslne=round(test_dom, 3), test_dostrojone=round(test_naj, 3), prob=len(study.trials),
                 okresy_walidacji=PUNKTY, okno=OKNO)
    (katalog / "parametry_optuna.json").write_text(json.dumps(wynik, indent=2), encoding="utf-8")
    print(f"\n  zapisano: {katalog / 'parametry_optuna.json'}" + ("  →  przetrenuj model: python main.py prognoza --trenuj" if uzyj else ""))
    return wynik


def parametry_modelu(katalog):
    """Parametry XGB dla modelu do pracy: dostrojone, jeśli strojenie wykazało zysk na teście, inaczej domyślne."""
    p = katalog / "parametry_optuna.json"
    if p.exists():
        w = json.loads(p.read_text(encoding="utf-8"))
        if w.get("uzyj"):
            return w["parametry"], "optuna"
    return domyslne(), "domyślne"


if __name__ == "__main__":
    main()
