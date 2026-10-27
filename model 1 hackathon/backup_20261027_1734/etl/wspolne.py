"""Wspólne przekształcenia: czas lokalny -> UTC, licznik narastający -> godziny, energia godzinowa -> UTC."""
import numpy as np
import pandas as pd

from .config import TZ


def lokalny_na_utc(t):
    """Czas lokalny ze zmianą czasu -> UTC. WAŻNE: wiersze w kolejności z pliku, bez NaT.
    Powtórzona godzina jesienią: odczyty przed pierwszym cofnięciem zegara w danym dniu = czas letni."""
    t = pd.Series(pd.to_datetime(t).values)
    cofniecie = t.diff() < pd.Timedelta(0)
    letni = ~cofniecie.groupby(t.dt.date).cumsum().astype(bool)
    return t.dt.tz_localize(TZ, ambiguous=letni.to_numpy(), nonexistent="shift_forward").dt.tz_convert("UTC")


def licznik_na_godziny(czas_utc, wartosc, max_luka="2h", reset_proc=0.01):
    """Licznik narastający -> przyrost na godzinę (indeks = początek godziny UTC).
    - zera i braki usuwane (przerwy transmisji),
    - spadek > reset_proc wartości = reset/wymiana licznika (nowy odcinek),
    - drobne spadki (błędne odczyty) usuwane przez bieżące maksimum,
    - przyrost po przerwie > max_luka = NaN (nie wiadomo, w której godzinie przybyło)."""
    s = pd.DataFrame({"t": pd.Series(czas_utc).reset_index(drop=True),          # .values zgubiłoby strefę
                      "v": pd.to_numeric(pd.Series(wartosc), errors="coerce").reset_index(drop=True)}).dropna()
    s = s[s["v"] > 0].sort_values("t", kind="stable").reset_index(drop=True)
    if s.empty:
        return pd.Series(dtype=float)
    odcinek = (s["v"].diff() < -reset_proc * s["v"].shift()).cumsum()
    s = s[s["v"] >= s.groupby(odcinek)["v"].cummax()]
    odcinek = odcinek.loc[s.index]
    s = s.assign(odc=odcinek.values).drop_duplicates("t", keep="last")
    d = s.groupby("odc")["v"].diff()
    d[s["t"].diff() > pd.Timedelta(max_luka)] = np.nan
    godz = s["t"].dt.floor("h")
    out = d.groupby(godz).sum(min_count=1)
    idx = pd.date_range(godz.min(), godz.max(), freq="h")       # zachowuje strefę (UTC)
    return out.reindex(idx)


def energia_koniec_godziny_na_utc(czas_lok, kwh):
    """Energia godzinowa ze znacznikiem KOŃCA godziny w czasie lokalnym -> indeks = początek godziny UTC.
    - nieistniejąca godzina (wiosna) -> usuwana,
    - powtórzona godzina (jesień): 2 wiersze -> letni/zimowy; 1 wiersz (2 h razem) -> dzielony na pół."""
    df = pd.DataFrame({"start": pd.to_datetime(pd.Series(czas_lok)).values - pd.Timedelta("1h"),
                       "v": pd.to_numeric(pd.Series(kwh), errors="coerce").values}).dropna(subset=["start"])
    loc = df["start"].dt.tz_localize(TZ, ambiguous="NaT", nonexistent="NaT")
    niejedn = loc.isna() & df["start"].dt.tz_localize(TZ, ambiguous=True, nonexistent="NaT").notna()
    czesci = [pd.Series(df.loc[loc.notna(), "v"].values, index=pd.DatetimeIndex(loc[loc.notna()]).tz_convert("UTC"))]
    for start, g in df[niejedn].groupby("start"):
        lato = pd.Timestamp(start).tz_localize(TZ, ambiguous=True).tz_convert("UTC")
        zima = pd.Timestamp(start).tz_localize(TZ, ambiguous=False).tz_convert("UTC")
        if len(g) >= 2:
            wart = [g["v"].iloc[0], g["v"].iloc[1]]
        else:
            wart = [g["v"].iloc[0] / 2] * 2
        czesci.append(pd.Series(wart, index=[lato, zima]))
    s = pd.concat(czesci).sort_index()
    return s[~s.index.duplicated(keep="first")]


def do_tabeli(seria, obiekt_id, kolumna, **stale):
    """Seria z indeksem czasu -> DataFrame [obiekt_id, czas, kolumna, ...] bez pustych wartości."""
    df = seria.rename(kolumna).rename_axis("czas").reset_index().dropna(subset=[kolumna])
    df.insert(0, "obiekt_id", obiekt_id)
    for k, v in stale.items():
        df[k] = v
    return df
