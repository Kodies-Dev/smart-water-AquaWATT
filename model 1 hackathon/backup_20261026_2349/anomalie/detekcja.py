"""Zespół trzech detektorów (Isolation Forest, LOF, One-Class SVM) z głosowaniem + reguły typu anomalii."""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler
from sklearn.svm import OneClassSVM

from .ustawienia import MIN_GLOSOW

KANDYDACI = ["nadwyzka_m3_proc", "noc_udzial", "kwh_na_m3_wzgl", "residual_proc", "nadwyzka_kwh_proc",
             "praca_wzgl", "poziom_max", "opad_doba", "opad_3d", "temp_sr", "topnienie_cm",
             # tryb panelowy (Detektor Anomalii GUS): nagła zmiana i odstawanie od innych pompowni tego samego dnia
             "nadwyzka_m3_proc_jump_score", "residual_proc_jump_score", "nadwyzka_kwh_proc_jump_score",
             "nadwyzka_m3_proc_zscore_miedzy", "residual_proc_zscore_miedzy", "nadwyzka_kwh_proc_zscore_miedzy"]
MODELE = ["IF", "LOF", "SVM"]
# cechy „skutku” – z nich wybieramy główną przyczynę; pogoda (opad, temperatura, roztopy) to kontekst, a nie przyczyna
SKUTKI = ["nadwyzka_m3_proc", "noc_udzial", "kwh_na_m3_wzgl", "residual_proc", "nadwyzka_kwh_proc", "praca_wzgl", "poziom_max"]
NAZWY_CECH = {
    "nadwyzka_m3_proc": "nadwyżka przepływu ponad bazę bezdeszczową [%]",
    "noc_udzial": "udział przepływu nocnego (02–05)",
    "kwh_na_m3_wzgl": "energia na m³ względem normy obiektu",
    "residual_proc": "energia ponad prognozę modelu [%]",
    "nadwyzka_kwh_proc": "energia ponad bazę bezdeszczową [%]",
    "praca_wzgl": "czas pracy pomp względem normy",
    "poziom_max": "maks. poziom w zbiorniku [cm]",
    "opad_doba": "opad doby [mm]",
    "opad_3d": "opad 3 dni [mm]",
    "temp_sr": "średnia temperatura [°C]",
    "topnienie_cm": "topnienie śniegu [cm]",
}
GLOSUJACE = {"IF": "Isolation Forest", "LOF": "LOF", "SVM": "One-Class SVM"}


def cechy_obiektu(g, min_pokrycie=0.5):
    """Cechy dostępne dla obiektu: pokrycie ≥ 60% dób i niestałe. Opad jest W cechach celowo:
    dużo wody przy ulewie to norma, dużo wody bez deszczu – anomalia."""
    return [c for c in KANDYDACI if g[c].notna().mean() >= min_pokrycie and g[c].nunique() > 1]


def wykryj(X, odsetek, seed=0):
    """Zwraca DataFrame z głosami 0/1 każdego modelu. Skalowanie odporne (mediana/IQR) – potrzebne LOF i SVM."""
    Z = RobustScaler().fit_transform(X)
    return pd.DataFrame({
        "IF": IsolationForest(n_estimators=300, contamination=odsetek, random_state=42).fit_predict(Z) == -1,
        "LOF": LocalOutlierFactor(n_neighbors=min(35, len(Z) - 1), contamination=odsetek).fit_predict(Z) == -1,
        "SVM": OneClassSVM(nu=odsetek, kernel="rbf", gamma="scale").fit_predict(Z) == -1,
    }, index=X.index).astype(int)


def z_odporny(X):
    """Odporny z-score: (x − mediana obiektu) / IQR. Mówi, o ile doba odstaje od normy tego obiektu w danej cesze."""
    iqr = (X.quantile(0.75) - X.quantile(0.25)).replace(0, np.nan)
    iqr = iqr.fillna(X.std().replace(0, np.nan)).fillna(1.0)
    return (X - X.median()) / iqr


def wykryj_wszystkie(dz, odsetek):
    """Detekcja osobno dla każdego obiektu (inne zachowanie, inny zestaw danych) + wyjaśnienie:
    główna przyczyna = cecha z największym |z-score| (jak build_row_facts w Detektorze Anomalii)."""
    wynik, zety, uzyte = [], [], {}
    for oid, g in dz.groupby("obiekt_id"):
        cols = cechy_obiektu(g)
        X = g[cols].dropna()
        uzyte[oid] = cols
        glosy = wykryj(X, odsetek) if len(X) > 50 else pd.DataFrame(0, index=X.index, columns=MODELE)
        wynik.append(glosy)
        zety.append(z_odporny(X).add_prefix("z_"))
    glosy = pd.concat(wynik).reindex(dz.index)
    z = pd.concat(zety).reindex(dz.index)
    out = dz.copy()
    out[MODELE] = glosy[MODELE]
    out["glosy"] = glosy[MODELE].sum(axis=1, min_count=1)
    out["anomalia"] = (out["glosy"] >= MIN_GLOSOW).where(out["glosy"].notna())
    out = out.join(z)
    zk = [f"z_{c}" for c in SKUTKI if f"z_{c}" in z.columns] or list(z.columns)
    absz = out[zk].abs()
    ma = absz.notna().any(axis=1)
    out["glowna_cecha"] = None
    out.loc[ma, "glowna_cecha"] = absz[ma].idxmax(axis=1).str.replace("z_", "", n=1)
    out["z_glownej"] = [out.at[i, f"z_{c}"] if isinstance(c, str) else np.nan for i, c in zip(out.index, out["glowna_cecha"])]
    return out, uzyte


def _wieksze(x, prog):
    return pd.notna(x) and x > prog


def typ_anomalii(r):
    """Reguły na danych dobowych. Nadwyżka: z przepływu (jeśli jest), inaczej z residualu energii."""
    nadmiar = _wieksze(r["nadwyzka_m3_proc"], 20) or _wieksze(r["residual_proc"], 15)
    niedobor = (pd.notna(r["nadwyzka_m3_proc"]) and r["nadwyzka_m3_proc"] < -30) or \
               (pd.notna(r["residual_proc"]) and r["residual_proc"] < -30)
    deszcz = _wieksze(r["opad_3d"], 5)
    sucho = pd.notna(r["opad_3d"]) and r["opad_3d"] < 2
    if nadmiar and deszcz:
        return "dopływ opadowy"
    if nadmiar and _wieksze(r["topnienie_cm"], 0.5) and _wieksze(r["temp_sr"], 0):
        return "roztopy"
    if nadmiar and sucho:
        return "infiltracja / dopływ bez deszczu" if _wieksze(r["noc_udzial"], 0.6) else "nadmiar bez deszczu"
    if niedobor:
        return "spadek – awaria / przerwa"
    if _wieksze(r["kwh_na_m3_wzgl"], 1.25):
        return "spadek sprawności pomp"
    if _wieksze(r.get("nastawy_odchylenie_cm"), 5) and r.get("glowna_cecha") in ("poziom_max", "praca_wzgl", None):
        return "zmiana nastaw sterowania"
    if _wieksze(r.get("z_poziom_max"), 2):                  # poziom w zbiorniku wyraźnie wyżej niż zwykle (SCADA RU)
        return "spiętrzenie w zbiorniku"
    return "inne / nietypowy dzień"


def _liczba(x, nd=1):
    return "–" if pd.isna(x) else f"{x:.{nd}f}"


def opis(r):
    """Jedno zdanie o anomalii – liczone w Pythonie, bez zgadywania."""
    c = r["glowna_cecha"]
    przyczyna = f"{NAZWY_CECH.get(c, c)} = {_liczba(r[c])} ({r['z_glownej']:+.1f} IQR od normy)" if isinstance(c, str) else "–"
    skala = f"{_liczba(r['skala_m3'], 0)} m³ ponad bazę" if pd.notna(r["skala_m3"]) else \
            f"{_liczba(r['skala_kwh'], 0)} kWh ponad prognozę" if pd.notna(r["skala_kwh"]) else "skala –"
    glosowaly = ", ".join(n for k, n in GLOSUJACE.items() if r.get(k) == 1) or "brak"
    dr = r.get(f"{c}_diff_from_rolling_mean") if isinstance(c, str) else None
    rolling = f"; różnica od średniej z 14 dób {_liczba(dr)}" if pd.notna(dr) else ""
    rodzaj = f"; rodzaj: {r['Rodzaj_Anomalii']}" if isinstance(r.get("Rodzaj_Anomalii"), str) else ""
    return (f"{r['obiekt_id']} {pd.Timestamp(r['dzien']):%Y-%m-%d}: {r['typ']}; główna przyczyna: {przyczyna}{rolling}; "
            f"{skala}; opad 3 dni {_liczba(r['opad_3d'])} mm; wykryta przez {int(r['glosy'])}/3 modeli: {glosowaly}{rodzaj}")


def nadaj_typy(df):
    df = df.copy()
    df["typ"] = np.where(df["anomalia"] == True, df.apply(typ_anomalii, axis=1), None)
    # skala: ile wód obcych (m³) albo energii (kWh) ponad normę tego dnia
    df["skala_m3"] = df["nadwyzka_m3"].where(df["anomalia"] == True)
    df["skala_kwh"] = df["residual_kwh"].where(df["anomalia"] == True)
    df["opis"] = None
    a = df["anomalia"] == True
    if a.any():
        df.loc[a, "opis"] = df[a].apply(opis, axis=1)
    return df
