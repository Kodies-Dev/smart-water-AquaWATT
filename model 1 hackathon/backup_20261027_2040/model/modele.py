"""Modele: baseline'y, regresja liniowa (Ridge), XGBoost (globalny, per obiekt, transfer).
Cel uczenia: y_log = log(1 + kWh / poziom); prognoza kWh = (exp(pred) - 1) * poziom."""
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .cechy import GRUPY
from .config import XGB


def kolumny(grupy):
    return [c for g in grupy for c in GRUPY[g]]


def _na_kwh(pred_log, df):
    return pd.Series(np.expm1(np.clip(pred_log, 0, None)) * df["poziom"].values, index=df.index)


def _xgb(tr, wal, X):
    m = xgb.XGBRegressor(**XGB)
    m.fit(tr[X], tr["y_log"], eval_set=[(wal[X], wal["y_log"])], verbose=False)
    return m


def trenuj_i_prognozuj(f, war):
    """Zwraca (prognoza kWh: test, prognoza kWh: walidacja, ważność cech albo None, info).
    Prognoza na walidacji służy do wyboru wariantu per obiekt (bez zaglądania w test)."""
    test, wal_all = f[f["zbior"] == "test"], f[f["zbior"] == "walidacja"]
    if war["typ"] == "baseline":
        return test[war["kolumna"]], wal_all[war["kolumna"]], None, ""

    X = kolumny(war["grupy"])
    tr, wal = f[f["zbior"] == "trening"], wal_all
    if "trening_obiekty" in war:
        tr, wal = tr[tr["obiekt_id"].isin(war["trening_obiekty"])], wal[wal["obiekt_id"].isin(war["trening_obiekty"])]
    if "test_obiekty" in war:
        test = test[test["obiekt_id"].isin(war["test_obiekty"])]

    if war["typ"] == "ridge":
        m = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(), Ridge(alpha=1.0))
        m.fit(tr[X], tr["y_log"])
        return _na_kwh(m.predict(test[X]), test), _na_kwh(m.predict(wal[X]), wal), None, ""

    if war.get("per_obiekt"):
        pred, pred_wal, drzewa = pd.Series(np.nan, index=test.index), pd.Series(np.nan, index=wal.index), []
        for oid, ti in test.groupby("obiekt_id"):
            wi = wal[wal["obiekt_id"] == oid]
            m = _xgb(tr[tr["obiekt_id"] == oid], wi, X)
            pred.loc[ti.index] = _na_kwh(m.predict(ti[X]), ti)
            pred_wal.loc[wi.index] = _na_kwh(m.predict(wi[X]), wi)
            drzewa.append(f"{oid}:{m.best_iteration + 1}")
        return pred, pred_wal, None, "drzew " + " ".join(drzewa)

    m = _xgb(tr, wal, X)
    waznosc = pd.Series(m.feature_importances_, index=X).sort_values(ascending=False)
    pred, pred_wal, info = _na_kwh(m.predict(test[X]), test), _na_kwh(m.predict(wal[X]), wal), f"drzew {m.best_iteration + 1}"
    if war.get("kalibracja"):
        k = kalibracja(m, wal, X)
        pred = pred * test["obiekt_id"].map(k).fillna(1.0)
        info += " | kalibracja " + " ".join(f"{o}:{v:.2f}" for o, v in k.items())
    return pred, pred_wal, waznosc, info


def kalibracja(m, wal, X, zakres=(0.7, 1.5)):
    """Mnożnik per obiekt = suma rzeczywista / suma prognozy na zbiorze walidacyjnym.
    Mediana nie liczy szczytów po ulewach, więc sumy wychodzą za małe – mnożnik wyrównuje sumę, zostawia kształt."""
    pw = _na_kwh(m.predict(wal[X]), wal)
    k = wal.groupby("obiekt_id")["kwh"].sum() / pw.groupby(wal["obiekt_id"]).sum()
    return k.clip(*zakres)
