"""Metryki i wykresy."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import TZ, MOKRY_DZIEN_MM


def _wape(doba):
    return 100 * (doba["pred"] - doba["kwh"]).abs().sum() / doba["kwh"].sum() if len(doba) else np.nan


def metryki(test, pred, nazwa):
    """Per obiekt + RAZEM: MAE, RMSE [kWh/h], WAPE godzinowe i dobowe [%], bias [%],
    WAPE dobowe osobno dla dób suchych i mokrych (opad > MOKRY_DZIEN_MM)."""
    d = test[["czas", "obiekt_id", "kwh", "opad_rz_1h"]].assign(pred=pred.clip(lower=0)).dropna(subset=["pred", "kwh"])
    d["dzien"] = d["czas"].dt.tz_convert(TZ).dt.date
    wiersze = []
    for oid, g in list(d.groupby("obiekt_id")) + [("RAZEM", d)]:
        e = g["pred"] - g["kwh"]
        doba = g.groupby(["obiekt_id", "dzien"])[["kwh", "pred", "opad_rz_1h"]].agg(["sum", "count"])
        doba = doba[doba[("kwh", "count")] >= 23].xs("sum", axis=1, level=1)      # tylko pełne doby (23–25 h)
        mokra = doba["opad_rz_1h"] > MOKRY_DZIEN_MM
        wiersze.append(dict(wariant=nazwa, obiekt=oid, godzin=len(g),
                            MAE=e.abs().mean(), RMSE=np.sqrt((e ** 2).mean()),
                            WAPE_h=100 * e.abs().sum() / g["kwh"].sum(),
                            WAPE_doba=_wape(doba),
                            WAPE_doba_sucho=_wape(doba[~mokra]), WAPE_doba_mokro=_wape(doba[mokra]),
                            doby_mokre=int(mokra.sum()), bias_proc=100 * e.sum() / g["kwh"].sum()))
    return wiersze


def wykres_obiektu(prog, met, oid, sciezka, top=3):
    """Test: dobowo cały okres + godzinowo pierwszy tydzień; rzeczywistość vs najlepsze warianty."""
    m = met[(met["obiekt"] == oid)].sort_values("WAPE_doba")
    najlepsze = [w for w in m["wariant"] if prog.loc[prog["obiekt_id"] == oid, w].notna().any()][:top]
    g = prog[prog["obiekt_id"] == oid].set_index("czas").sort_index()
    lok = g.index.tz_convert(TZ)
    fig, ax = plt.subplots(2, 1, figsize=(15, 8))
    dz = g[["kwh", *najlepsze]].groupby(lok.date).sum(min_count=1)
    dz = dz[g["kwh"].groupby(lok.date).count() >= 23]                             # tylko pełne doby
    ax[0].plot(dz.index, dz["kwh"], color="k", lw=1.5, label="rzeczywiste")
    for w in najlepsze:
        ax[0].plot(dz.index, dz[w], lw=1, label=f"{w} (WAPE doba {m.set_index('wariant').loc[w, 'WAPE_doba']:.1f}%)")
    ax[0].set_title(f"{oid} – test, kWh / dobę"); ax[0].legend()
    t = g.iloc[:168]
    ax[1].plot(t.index.tz_convert(TZ), t["kwh"], color="k", lw=1.5, label="rzeczywiste")
    for w in najlepsze:
        ax[1].plot(t.index.tz_convert(TZ), t[w], lw=1, label=w)
    ax[1].set_title("pierwszy tydzień testu, kWh / h"); ax[1].legend()
    plt.tight_layout(); plt.savefig(sciezka, dpi=90); plt.close(fig)


def wykres_waznosci(waz, nazwa, sciezka, top=20):
    fig, ax = plt.subplots(figsize=(8, 6))
    waz.head(top)[::-1].plot.barh(ax=ax)
    ax.set_title(f"Ważność cech – {nazwa}")
    plt.tight_layout(); plt.savefig(sciezka, dpi=90); plt.close(fig)
