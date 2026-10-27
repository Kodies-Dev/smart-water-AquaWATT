"""
Adapter: nasz potok anomalii (pakiet anomalie/ w projekcie) podany w formacie wyników Detektora Anomalii GUS
(anomaly_d.py). Dzięki temu zakładki Raport i Pytanie oraz istniejące wykresy działają bez zmian - dostają te same
kolumny: Anomaly_IF / _LOF / _SVM / _Votes / _Final, {kol}_zscore, {kol}_diff_from_rolling_mean, {kol}_is_outlier,
Has_Outlier, Nagla_Zmiana, Odstaje_Od_Innych, Rodzaj_Anomalii.

Różnica względem anomaly_d.py: nie liczymy cech z dowolnych kolumn pliku, tylko cechy hydrologiczne per pompownia
i doba (baza bezdeszczowa, nadwyżka przepływu, przepływ nocny, residual prognozy energii, kWh/m³, opad), a zespół
IF + LOF + One-Class SVM działa osobno dla każdej pompowni.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

KATALOG_PROJEKTU = Path(__file__).resolve().parents[2]           # aplikacja/backend_ml_llm -> projekt
if str(KATALOG_PROJEKTU) not in sys.path:
    sys.path.insert(0, str(KATALOG_PROJEKTU))

from anomalie.cechy_dobowe import dzienne                          # noqa: E402
from anomalie.detekcja import wykryj_wszystkie, nadaj_typy, SKUTKI, NAZWY_CECH, MODELE   # noqa: E402
from anomalie.ocena_anomalii import dni_alarmow, ranking, przyczyny, znane_zdarzenia  # noqa: E402
from anomalie.panel import dodaj_cechy_panelowe, dodaj_rodzaj     # noqa: E402
from anomalie.uruchom import dobierz_odsetek, wczytaj_alarmy      # noqa: E402

KOLUMNY_GODZINOWE = ["obiekt_id", "czas", "kwh", "m3", "opad_mm", "temp_c"]   # format wgrywanego CSV


class nasz_detektor:

    # ---------------------------------------------------------------- dane

    @staticmethod
    def dane_z_bazy():
        """Tabele z bazy po ETL (jak w model/dane.py) + alarmy CH do doboru odsetka."""
        from model.dane import wczytaj
        return wczytaj(), wczytaj_alarmy()

    @staticmethod
    def dane_z_godzinowego(df: pd.DataFrame):
        """Wgrany CSV godzinowy -> słownik tabel w formacie bazy. Wymagane: czas, kwh. Opcjonalne: obiekt_id
        (domyślnie 'OBIEKT'), m3, opad_mm, temp_c. Czas traktowany jako początek godziny w UTC."""
        df = df.copy()
        if "czas" not in df or "kwh" not in df:
            raise ValueError("Plik musi mieć kolumny 'czas' i 'kwh' (opcjonalnie: obiekt_id, m3, opad_mm, temp_c).")
        if "obiekt_id" not in df:
            df["obiekt_id"] = "OBIEKT"
        df["obiekt_id"] = df["obiekt_id"].astype(str)
        df["czas"] = pd.to_datetime(df["czas"], utc=True, errors="coerce")
        df = df.dropna(subset=["czas"])
        for c in ["kwh", "m3", "opad_mm", "temp_c"]:
            df[c] = pd.to_numeric(df[c], errors="coerce") if c in df else np.nan
        pogoda = df[["obiekt_id", "czas", "opad_mm", "temp_c"]].rename(columns={"obiekt_id": "stacja"})
        for c in ["deszcz_mm", "snieg_cm", "pokrywa_m", "wilg_gleby_0_7", "wilg_gleby_7_28", "et0_mm"]:
            pogoda[c] = np.nan
        from etl.zewnetrzne import kalendarz
        obiekty = pd.DataFrame({"obiekt_id": sorted(df["obiekt_id"].unique())})
        obiekty["stacja_pogody"] = obiekty["obiekt_id"]
        for c in ["moc_pompy_kw", "wydajnosc_m3h", "zbiornik_m3"]:
            obiekty[c] = np.nan
        puste = lambda kol: pd.DataFrame(columns=kol)
        return dict(energia=df[["obiekt_id", "czas", "kwh"]].dropna(), przeplyw=df[["obiekt_id", "czas", "m3"]].dropna(),
                    scada=puste(["obiekt_id", "czas", "praca_pomp_h", "poziom_max"]),
                    opad_ru=puste(["czas", "mm"]), pogoda=pogoda, prognoza=puste(["stacja", "czas", "opad_mm", "temp_c", "snieg_cm"]),
                    kalendarz=kalendarz(lambda *a: None), obiekty=obiekty)

    @staticmethod
    def dobowo_do_podgladu(d):
        """Tabela dobowa per obiekt do zakładek Dane i Wykresy (kWh, m³, opad)."""
        e = d["energia"].assign(dzien=d["energia"]["czas"].dt.tz_convert("Europe/Warsaw").dt.date)
        t = e.groupby(["obiekt_id", "dzien"])["kwh"].sum().rename("kwh_doba").reset_index()
        if len(d["przeplyw"]):
            p = d["przeplyw"].assign(dzien=d["przeplyw"]["czas"].dt.tz_convert("Europe/Warsaw").dt.date)
            t = t.merge(p.groupby(["obiekt_id", "dzien"])["m3"].sum().rename("m3_doba").reset_index(), how="left")
        t["dzien"] = pd.to_datetime(t["dzien"])
        return t.sort_values(["obiekt_id", "dzien"]).reset_index(drop=True)

    # ---------------------------------------------------------------- detekcja

    @staticmethod
    def cechy(d, okno=14):
        """Cechy dobowe (z prognozą energii out-of-fold) + tryb panelowy."""
        return dodaj_cechy_panelowe(dzienne(d), okno=okno)

    @staticmethod
    def dobierz_odsetek(dz, alarmy):
        return dobierz_odsetek(dz, dni_alarmow(alarmy))

    @staticmethod
    def detect(dz, odsetek=0.05):
        """Zespół IF + LOF + One-Class SVM (>= 2 z 3) per pompownia, typ, rodzaj, główna przyczyna, opis.
        Zwraca (wynik z kolumnami jak w anomaly_d.py, num_cols, cechy użyte per obiekt)."""
        wynik, uzyte = wykryj_wszystkie(dz, odsetek)
        wynik = nadaj_typy(dodaj_rodzaj(wynik))
        return nasz_detektor.aliasy(wynik) + (uzyte,)

    @staticmethod
    def aliasy(w):
        """Nazwy kolumn z Detektora GUS. num_cols = cechy „skutku” (woda, energia, pompy) - z nich report_generator
        wybiera główną przyczynę po najwyższym |z-score|, tak jak nasz potok."""
        w = w.copy()
        for m in MODELE:
            w[f"Anomaly_{m}"] = w[m].fillna(0).astype(int)
        w["Anomaly_Votes"] = w["glosy"].fillna(0).astype(int)
        w["Anomaly_Final"] = (w["anomalia"] == True).astype(int)
        num_cols = [c for c in SKUTKI if f"z_{c}" in w and w[f"z_{c}"].notna().any()]
        for c in num_cols:
            w[f"{c}_zscore"] = w[f"z_{c}"].fillna(0)
        w["dzien"] = pd.to_datetime(w["dzien"])
        w.index = w["obiekt_id"] + " " + w["dzien"].dt.strftime("%Y-%m-%d")   # „Wiersz RU_W 2025-03-05” w raporcie
        w.index.name = "obiekt_doba"
        return w, num_cols

    @staticmethod
    def podsumowania(wynik, alarmy=None):
        """Ranking wód obcych, przyczyny, znane zdarzenia - jak w python main.py anomalie."""
        licz, roz, per_typ = przyczyny(wynik.reset_index(drop=True))
        return dict(ranking=ranking(wynik.reset_index(drop=True)), przyczyny=licz, rozroznianie=roz, per_typ=per_typ,
                    znane=znane_zdarzenia(wynik.reset_index(drop=True)))

    NAZWY_CECH = NAZWY_CECH
