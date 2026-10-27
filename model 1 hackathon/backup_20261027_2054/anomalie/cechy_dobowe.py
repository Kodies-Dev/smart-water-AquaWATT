"""Cechy dobowe do wykrywania anomalii: baza bezdeszczowa, nadwyżki, przepływ nocny, residual energii, pogoda."""
import numpy as np
import pandas as pd
import xgboost as xgb

from model.cechy import zbuduj, kolumny_grup
from .ustawienia import TZ, SUCHO_H, SUCHO_MM, NOC, MIN_GODZIN, FOLDY, XGB_OOF

GRUPY_OOF = ["kalendarz", "lagi", "obiekt", "opad_przeszly", "opad_rzeczywisty", "pogoda_rzeczywista"]


def prognoza_oof(d):
    """Prognoza kWh/h dla KAŻDEJ godziny: czas obiektu dzielony na FOLDY bloków, blok prognozuje model uczony na reszcie.
    Pogoda zmierzona (nie prognoza) – szukamy zużycia, którego pogoda nie tłumaczy."""
    f = zbuduj(d)
    f = f[f["y_log"].notna() & f["poziom"].notna() & f["b_profil_4tyg"].notna()].copy()
    X = kolumny_grup(GRUPY_OOF)
    f["blok"] = f.groupby("obiekt_id")["czas"].transform(lambda t: pd.qcut(t.rank(method="first"), FOLDY, labels=False))
    pred = pd.Series(np.nan, index=f.index)
    for k in range(FOLDY):
        tr, te = f[f["blok"] != k], f[f["blok"] == k]
        m = xgb.XGBRegressor(**XGB_OOF).fit(tr[X], tr["y_log"])
        pred[te.index] = np.expm1(np.clip(m.predict(te[X]), 0, None)) * te["poziom"].values
    return f[["obiekt_id", "czas"]].assign(kwh_pred=pred)


def _siatka(df, idx, kol):
    if df is None or df.empty:
        return pd.Series(np.nan, index=idx)
    return df.drop_duplicates("czas").set_index("czas")[kol].reindex(idx)


def baza_sucha(s, opad):
    """Baza bezdeszczowa (dry weather flow): mediana per dzień tygodnia × godzina z godzin bez opadu przez SUCHO_H h."""
    if s.notna().sum() == 0:
        return pd.Series(np.nan, index=s.index)
    sucho = (opad.fillna(0).rolling(SUCHO_H, min_periods=1).sum() < SUCHO_MM) & s.notna()
    lok = s.index.tz_convert(TZ)
    klucz = pd.MultiIndex.from_arrays([lok.day_of_week, lok.hour])
    prof = pd.Series(s.values, index=klucz)[sucho.values].groupby(level=[0, 1]).median()
    return pd.Series(prof.reindex(klucz).values, index=s.index)


def dzienne_obiektu(oid, d, obiekt, oof):
    en = d["energia"][d["energia"]["obiekt_id"] == oid]
    idx = pd.date_range(en["czas"].min(), en["czas"].max(), freq="h", name="czas")
    kwh = _siatka(en, idx, "kwh")
    m3 = _siatka(d["przeplyw"][d["przeplyw"]["obiekt_id"] == oid], idx, "m3")
    p = d["pogoda"][d["pogoda"]["stacja"] == obiekt["stacja_pogody"]]
    opad = _siatka(p, idx, "opad_mm")
    if oid.startswith("RU"):                                      # w Rudzie deszczomierz, braki uzupełnia ERA5
        opad = _siatka(d["opad_ru"], idx, "mm").fillna(opad)
    sc = d["scada"][d["scada"]["obiekt_id"] == oid]
    h = pd.DataFrame({
        "kwh": kwh, "m3": m3, "opad": opad,
        "kwh_baza": baza_sucha(kwh, opad), "m3_baza": baza_sucha(m3, opad),
        "kwh_pred": _siatka(oof[oof["obiekt_id"] == oid], idx, "kwh_pred"),
        "temp": _siatka(p, idx, "temp_c"), "pokrywa": _siatka(p, idx, "pokrywa_m"),
        "praca": _siatka(sc, idx, "praca_pomp_h"), "poziom": _siatka(sc, idx, "poziom_max"),
        "prog_start": _siatka(sc, idx, "prog_start") if "prog_start" in sc else np.nan,
        "prog_stop": _siatka(sc, idx, "prog_stop") if "prog_stop" in sc else np.nan,
    }, index=idx)
    lok = idx.tz_convert(TZ)
    h["dzien"] = lok.date
    h["noc"] = (lok.hour >= NOC[0]) & (lok.hour <= NOC[1])
    g = h.groupby("dzien")
    suma = lambda c: g[c].sum(min_count=1).where(g[c].count() >= MIN_GODZIN)
    dz = pd.DataFrame({
        "kwh": suma("kwh"), "kwh_baza": suma("kwh_baza"), "kwh_pred": suma("kwh_pred"),
        "m3": suma("m3"), "m3_baza": suma("m3_baza"),
        "noc_m3": h[h["noc"]].groupby("dzien")["m3"].mean(), "srednio_m3": g["m3"].mean(),
        "opad_doba": g["opad"].sum(min_count=1), "temp_sr": g["temp"].mean(), "pokrywa": g["pokrywa"].mean(),
        "praca_h": suma("praca"), "poziom_max": g["poziom"].max(),
        "prog_start": g["prog_start"].median(), "prog_stop": g["prog_stop"].median(),
    })
    dz.index = pd.to_datetime(dz.index)
    dz["opad_3d"] = dz["opad_doba"].rolling(3, min_periods=1).sum()
    dz["topnienie_cm"] = ((dz["pokrywa"].shift(1) - dz["pokrywa"]) * 100).clip(lower=0)
    dz["nadwyzka_m3"] = dz["m3"] - dz["m3_baza"]
    dz["nadwyzka_m3_proc"] = 100 * dz["nadwyzka_m3"] / dz["m3_baza"]
    dz["noc_udzial"] = dz["noc_m3"] / dz["srednio_m3"]             # przepływ nocny / średni – wysoki = infiltracja
    dz["nadwyzka_kwh"] = dz["kwh"] - dz["kwh_baza"]
    dz["nadwyzka_kwh_proc"] = 100 * dz["nadwyzka_kwh"] / dz["kwh_baza"]
    dz["residual_kwh"] = dz["kwh"] - dz["kwh_pred"]
    dz["residual_proc"] = 100 * dz["residual_kwh"] / dz["kwh_pred"]
    dz["kwh_na_m3_wzgl"] = (dz["kwh"] / dz["m3"]) / (dz["kwh"] / dz["m3"]).median()
    dz["praca_wzgl"] = dz["praca_h"] / dz["praca_h"].median()
    # nastawy sterowania pomp (progi start/stop z SCADA) inne niż zwykle dla obiektu – np. RU_ZMP w 2026 (stop 50 -> 60-70 cm)
    dz["nastawy_odchylenie_cm"] = pd.concat([(dz["prog_start"] - dz["prog_start"].median()).abs(),
                                             (dz["prog_stop"] - dz["prog_stop"].median()).abs()], axis=1).max(axis=1)
    dz.insert(0, "obiekt_id", oid)
    return dz.rename_axis("dzien").reset_index()


def dzienne(d):
    oof = prognoza_oof(d)
    obiekty = d["obiekty"].set_index("obiekt_id")
    return pd.concat([dzienne_obiektu(o, d, obiekty.loc[o], oof) for o in sorted(d["energia"]["obiekt_id"].unique())],
                     ignore_index=True)
