"""Cechy panelowe – na wzór trybu szeregów czasowych w Detektorze Anomalii (GUS, anomaly_d.py).
Jednostka = pompownia (obiekt_id), okres = doba. Nazwy kolumn jak w tamtym projekcie."""
import numpy as np
import pandas as pd

from .ustawienia import OKNO_PANEL, PROG_RODZAJ, MIN_OBIEKTOW_DOBA, PANEL_BAZA


def _odstawanie_od_innych(df, c, min_obiektow=MIN_OBIEKTOW_DOBA):
    """Wersja odporna na małą liczbę jednostek. Klasyczny z-score przekroju (jak w Detektorze GUS) przy n jednostkach
    nie przekracza (n−1)/√n – przy 4 pompowniach to 1,5, więc próg 2,0 byłby nieosiągalny. Zamiast tego:
    d = wartość obiektu − mediana POZOSTAŁYCH obiektów tego dnia, skalowane typową różnicą tego obiektu (mediana, IQR)."""
    p = df.pivot_table(index="dzien", columns="obiekt_id", values=c)
    wynik = pd.Series(np.nan, index=df.index)
    for oid in p.columns:
        inni = p.drop(columns=oid)
        mediana_innych = inni.median(axis=1).where(inni.notna().sum(axis=1) >= min_obiektow - 1)
        d = p[oid] - mediana_innych
        iqr = d.quantile(0.75) - d.quantile(0.25)
        z = (d - d.median()) / (iqr if iqr and np.isfinite(iqr) else np.nan)
        m = df["obiekt_id"] == oid
        wynik[m] = df.loc[m, "dzien"].map(z).values
    return wynik


def dodaj_cechy_panelowe(dz, kolumny=PANEL_BAZA, okno=OKNO_PANEL):
    df = dz.sort_values(["obiekt_id", "dzien"]).copy()
    g = df.groupby("obiekt_id", sort=False)
    for c in kolumny:
        # nagła zmiana: o ile odchyleń WŁASNEJ historii (poprzednich `okno` dób) skoczyła wartość
        sr = g[c].transform(lambda s: s.rolling(okno, min_periods=3).mean().shift(1))
        sd = g[c].transform(lambda s: s.rolling(okno, min_periods=3).std().shift(1)).replace(0, np.nan)
        df[f"{c}_diff_from_rolling_mean"] = df[c] - sr
        df[f"{c}_jump_score"] = df[f"{c}_diff_from_rolling_mean"] / sd
        # nietypowość na tle własnej historii obiektu
        df[f"{c}_zscore_wlasny"] = (df[c] - g[c].transform("mean")) / g[c].transform("std").replace(0, np.nan)
        # odstawanie od innych pompowni TEGO SAMEGO DNIA (ta sama pogoda)
        df[f"{c}_zscore_miedzy"] = _odstawanie_od_innych(df, c)
        # flaga outlier IQR (per obiekt)
        q1, q3 = g[c].transform(lambda s: s.quantile(0.25)), g[c].transform(lambda s: s.quantile(0.75))
        iqr = q3 - q1
        df[f"{c}_is_outlier"] = ((df[c] < q1 - 1.5 * iqr) | (df[c] > q3 + 1.5 * iqr)).astype(int).where(df[c].notna())
    df["Has_Outlier"] = df[[f"{c}_is_outlier" for c in kolumny]].sum(axis=1, min_count=1)
    return df.sort_index()


def dodaj_rodzaj(df, kolumny=PANEL_BAZA, prog=PROG_RODZAJ):
    """Rodzaj anomalii jak w Detektorze: nagła zmiana (własna historia) / odstaje od innych (ten sam dzień) / oba."""
    jump = [f"{c}_jump_score" for c in kolumny if f"{c}_jump_score" in df]
    cross = [f"{c}_zscore_miedzy" for c in kolumny if f"{c}_zscore_miedzy" in df]
    df = df.copy()
    df["Nagla_Zmiana"] = df[jump].abs().max(axis=1) if jump else np.nan
    df["Odstaje_Od_Innych"] = df[cross].abs().max(axis=1) if cross else np.nan
    nagla, odstaje = df["Nagla_Zmiana"] > prog, df["Odstaje_Od_Innych"] > prog
    rodzaj = np.select([nagla & odstaje, nagla, odstaje],
                       ["nagła zmiana + odstaje od innych", "nagła zmiana", "odstaje od innych"],
                       default="brak wyraźnego wzorca")
    df["Rodzaj_Anomalii"] = pd.Series(rodzaj, index=df.index).where(df["anomalia"] == True)
    return df
