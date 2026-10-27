"""Walidacja na alarmach CH, znane zdarzenia, ranking obiektów, wykresy."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .ustawienia import TZ, TOLERANCJA_DNI, ALARMY_KATEGORIE, ZNANE_ZDARZENIA
from .detekcja import MODELE, NAZWY_CECH

KOLORY = {"dopływ opadowy": "#378ADD", "roztopy": "#85B7EB", "infiltracja / dopływ bez deszczu": "#D85A30",
          "nadmiar bez deszczu": "#EF9F27", "spadek – awaria / przerwa": "#A32D2D",
          "spadek sprawności pomp": "#7F77DD", "zmiana nastaw sterowania": "#5DCAA5",
          "spiętrzenie w zbiorniku": "#993556",
          "inne / nietypowy dzień": "#888780"}


def dni_alarmow(alarmy):
    """Dni (lokalnie) z aktywnym alarmem per kategoria."""
    if alarmy is None or alarmy.empty:
        return {}
    a = alarmy[alarmy["stan"] == 1].copy()
    a["dzien"] = pd.to_datetime(a["czas"], utc=True).dt.tz_convert(TZ).dt.tz_localize(None).dt.normalize()
    return {k: set(a.loc[a["sygnal"].isin(s), "dzien"]) for k, s in ALARMY_KATEGORIE.items()}


def _blisko(dni, cele, tol=TOLERANCJA_DNI):
    cele = np.array(sorted(cele), dtype="datetime64[ns]")
    if len(cele) == 0:
        return np.zeros(len(dni), dtype=bool)
    dni = np.array(dni, dtype="datetime64[ns]")
    pos = np.searchsorted(cele, dni)
    roz = np.full(len(dni), np.inf)
    for p in (pos - 1, pos):
        ok = (p >= 0) & (p < len(cele))
        roz[ok] = np.minimum(roz[ok], np.abs((dni[ok] - cele[p[ok]]) / np.timedelta64(1, "D")))
    return roz <= tol


def walidacja_ch(df, alarmy_dni, odsetek):
    """Dla każdego modelu i zespołu: % dni alarmowych złapanych (±1 doba), % wskazań przy alarmach i lift vs losowo."""
    ch = df[(df["obiekt_id"] == "CH_T") & df["glosy"].notna()]
    if ch.empty or not alarmy_dni:
        return pd.DataFrame()
    wszystkie = set().union(*alarmy_dni.values())
    baza = _blisko(ch["dzien"], wszystkie).mean()                 # szansa trafienia losowym dniem
    wiersze = []
    for nazwa, maska in [*[(m, ch[m] == 1) for m in MODELE], ("zespół (≥2 z 3)", ch["anomalia"] == True)]:
        wsk = ch.loc[maska, "dzien"]
        traf = _blisko(wsk, wszystkie).mean() if len(wsk) else np.nan
        w = dict(odsetek=odsetek, model=nazwa, wskazanych_dni=len(wsk), trafienia_przy_alarmie_proc=100 * traf,
                 lift=traf / baza if baza else np.nan)
        for kat, dni in alarmy_dni.items():
            if dni:
                w[f"zlapane_{kat}_proc"] = 100 * _blisko(sorted(dni), wsk).mean() if len(wsk) else 0.0
        w["zlapane_wszystkie_proc"] = 100 * _blisko(sorted(wszystkie), wsk).mean() if len(wsk) else 0.0
        wiersze.append(w)
    return pd.DataFrame(wiersze)


def znane_zdarzenia(df):
    wiersze = []
    for nazwa, obiekty, od, do in ZNANE_ZDARZENIA:
        for oid in obiekty:
            g = df[(df["obiekt_id"] == oid) & (df["dzien"] >= od) & (df["dzien"] <= do)]
            if g.empty:
                continue
            wykryte = g[g["anomalia"] == True]
            wiersze.append(dict(zdarzenie=nazwa, obiekt=oid, dni=len(g), wykryte_dni=len(wykryte),
                                typy=", ".join(sorted(set(wykryte["typ"].dropna()))) or "–"))
    return pd.DataFrame(wiersze)


def ranking(df):
    """Reguły, niezależnie od ML: ile wód obcych ma obiekt i jak reaguje na deszcz."""
    wiersze = []
    for oid, g in df.groupby("obiekt_id"):
        r = dict(obiekt=oid, dni=len(g), anomalii=int((g["anomalia"] == True).sum()))
        m = g.dropna(subset=["m3", "m3_baza"])
        if len(m) > 30:
            r["udzial_wod_obcych_proc"] = 100 * m["nadwyzka_m3"].clip(lower=0).sum() / m["m3"].sum()
            mokre = m[m["opad_doba"] >= 2]
            r["reakcja_m3_na_mm"] = (mokre["nadwyzka_m3"] / mokre["opad_doba"]).median() if len(mokre) else np.nan
            r["noc_udzial_sucho"] = m.loc[m["opad_3d"] < 1, "noc_udzial"].median()
        e = g.dropna(subset=["kwh", "kwh_baza"])
        if len(e) > 30:
            r["nadwyzka_energii_proc"] = 100 * e["nadwyzka_kwh"].clip(lower=0).sum() / e["kwh"].sum()
            mokre = e[e["opad_doba"] >= 2]
            r["reakcja_kwh_na_mm"] = (mokre["nadwyzka_kwh"] / mokre["opad_doba"]).median() if len(mokre) else np.nan
        for t, n in g["typ"].value_counts().items():
            r[f"typ: {t}"] = int(n)
        wiersze.append(r)
    return pd.DataFrame(wiersze).fillna({c: 0 for c in [] })


def wykres_obiektu(df, oid, sciezka, alarmy_dni=None):
    g = df[df["obiekt_id"] == oid].set_index("dzien")
    przeplyw = g["m3"].notna().mean() > 0.6
    y, baza, jedn = ("m3", "m3_baza", "m³") if przeplyw else ("kwh", "kwh_baza", "kWh")
    fig, ax = plt.subplots(figsize=(15, 5))
    ax.plot(g.index, g[y], color="black", lw=0.8, label=f"rzeczywiste [{jedn}/dobę]")
    ax.plot(g.index, g[baza], color="#1D9E75", lw=1, alpha=0.8, label="baza bezdeszczowa")
    for t, k in KOLORY.items():
        a = g[(g["anomalia"] == True) & (g["typ"] == t)]
        if len(a):
            ax.scatter(a.index, a[y], color=k, s=28, zorder=3, label=f"{t} ({len(a)})")
    if alarmy_dni and oid == "CH_T":
        for d in sorted(set().union(*alarmy_dni.values())):
            ax.axvline(d, color="#A32D2D", alpha=0.12, lw=2)
    a2 = ax.twinx()
    a2.bar(g.index, g["opad_doba"], color="#378ADD", alpha=0.25, width=1)
    a2.set_ylim(0, max(1, g["opad_doba"].max()) * 3)
    a2.set_ylabel("opad [mm/dobę]")
    ax.set_title(f"{oid} – anomalie (głosowanie ≥ 2 z 3: Isolation Forest, LOF, One-Class SVM)"
                 + (" | czerwone pasy = alarmy tłoczni" if oid == "CH_T" and alarmy_dni else ""))
    ax.legend(loc="upper left", fontsize=8)
    plt.tight_layout(); plt.savefig(sciezka, dpi=90); plt.close(fig)


def wykres_rankingu(rank, sciezka):
    cols = [c for c in ["udzial_wod_obcych_proc", "nadwyzka_energii_proc"] if c in rank]
    ax = rank.set_index("obiekt")[cols].rename(columns={"udzial_wod_obcych_proc": "wody obce w przepływie [%]",
                                                        "nadwyzka_energii_proc": "energia ponad bazę bezdeszczową [%]"}).plot.bar(figsize=(10, 4.5))
    ax.set_title("Ranking obiektów – ile wody / energii ponad normę bezdeszczową"); ax.set_xlabel("")
    ax.grid(axis="y", alpha=0.3); plt.xticks(rotation=0); plt.tight_layout(); plt.savefig(sciezka, dpi=90); plt.close()


def przyczyny(df):
    """Co wyróżnia anomalie: jak często cecha była główną przyczyną + mediana |z| w dobach z anomalią vs bez."""
    a = df[df["anomalia"] == True]
    if a.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    licz = a["glowna_cecha"].value_counts().rename("anomalii").to_frame()
    licz["udzial_proc"] = 100 * licz["anomalii"] / licz["anomalii"].sum()
    licz["nazwa"] = licz.index.map(lambda c: NAZWY_CECH.get(c, c))
    zk = [c for c in df.columns if c.startswith("z_") and c != "z_glownej"]
    n = df[df["anomalia"] == False]
    roz = pd.DataFrame({"mediana_abs_z_anomalie": a[zk].abs().median(), "mediana_abs_z_normalne": n[zk].abs().median()})
    roz["krotnosc"] = roz["mediana_abs_z_anomalie"] / roz["mediana_abs_z_normalne"].replace(0, np.nan)
    roz.index = roz.index.str.replace("z_", "", n=1)
    roz["nazwa"] = roz.index.map(lambda c: NAZWY_CECH.get(c, c))
    per_typ = a.groupby(["typ", "glowna_cecha"]).size().unstack(fill_value=0)
    return licz, roz.sort_values("krotnosc", ascending=False), per_typ


def wykres_przyczyn(licz, roz, sciezka):
    fig, ax = plt.subplots(1, 2, figsize=(15, 4.8))
    l = licz.sort_values("anomalii")
    ax[0].barh(l["nazwa"], l["udzial_proc"], color="#D85A30")
    ax[0].set_title("Główna przyczyna anomalii (% anomalii)"); ax[0].set_xlabel("%")
    r = roz.dropna(subset=["krotnosc"]).sort_values("krotnosc")
    ax[1].barh(r["nazwa"], r["krotnosc"], color="#378ADD")
    ax[1].axvline(1, color="black", lw=0.8)
    ax[1].set_title("Na ile cecha odróżnia anomalie od zwykłych dób\n(mediana |z| anomalii / zwykłych)")
    plt.tight_layout(); plt.savefig(sciezka, dpi=90); plt.close(fig)
