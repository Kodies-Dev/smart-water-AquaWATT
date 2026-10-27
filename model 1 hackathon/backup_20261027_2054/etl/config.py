"""Konfiguracja ETL. Wartości można nadpisać zmiennymi środowiskowymi (robi to docker-compose)."""
import os
from pathlib import Path

DB_URL = os.environ.get("DB_URL", "postgresql+psycopg2://hack:hack@127.0.0.1:5435/smartwater")
DANE = Path(os.environ.get("DANE_DIR", Path(__file__).resolve().parents[1] / "Dane"))

CACHE = Path(os.environ.get("CACHE_DIR", Path(__file__).resolve().parents[1] / "cache"))   # pobrana pogoda

CH = DANE / "CH" / "Dane do konkursu"
RU = DANE / "RU"
RY = DANE / "RY"

TZ = "Europe/Warsaw"

# Okresy do odcięcia (artefakty) – do weryfikacji
ODETNIJ_PRZEPLYW_DO = {
    "RY_PZ1": "2024-04-01",   # rozruch / nowy licznik przełom II–III 2024
}

# Metadane obiektów (schemat Rybnika + szacunki z danych dla CH i RU)
OBIEKTY = [
    dict(obiekt_id="CH_T", miasto="CH", nazwa="Tłocznia Chorzów", opis="1 pompa naraz, 3 pompy (P1–P3)",
         liczba_pomp=3, moc_pompy_kw=None, wydajnosc_m3h=368.0, zbiornik_m3=None, zrodlo_param="przeplywowe.csv", stacja_pogody="CH"),
    dict(obiekt_id="RU_W", miasto="RU", nazwa="Pompownia W", opis="licznik przepływu w SCADA (k06)",
         liczba_pomp=2, moc_pompy_kw=5.0, wydajnosc_m3h=20.0, zbiornik_m3=None, zrodlo_param="szacunek z SCADA", stacja_pogody="RU"),
    dict(obiekt_id="RU_ZMP", miasto="RU", nazwa="Pompownia ZMP (T?)", opis="brak przepływomierza",
         liczba_pomp=2, moc_pompy_kw=13.0, wydajnosc_m3h=None, zbiornik_m3=None, zrodlo_param="szacunek z SCADA", stacja_pogody="RU"),
    dict(obiekt_id="RY_PNB1", miasto="RY", nazwa="PNB1 ul. Sztygarska, Niedobczyce", opis="na schemacie 'PNB 6'",
         liczba_pomp=2, moc_pompy_kw=15.0, wydajnosc_m3h=47.5, zbiornik_m3=45.7, zrodlo_param="schemat Rybnik", stacja_pogody="RY"),
    dict(obiekt_id="RY_PZ1", miasto="RY", nazwa="PZ1 ul. Dolna, Zamysłów", opis="na schemacie 'PZ 2'",
         liczba_pomp=2, moc_pompy_kw=11.0, wydajnosc_m3h=330.0, zbiornik_m3=124.35, zrodlo_param="schemat Rybnik", stacja_pogody="RY"),
]

# Pogoda z Open-Meteo (ERA5): przybliżone położenie obiektów – siatka modelu ma kilka–kilkanaście km
POGODA_OD = "2023-01-01"
PROGNOZA_OD = "2024-01-01"   # Previous Runs API (prognoza wydana dzień wcześniej) ma dane od stycznia 2024
POGODA_PUNKTY = {
    "CH": (50.30, 18.95),   # Chorzów
    "RU": (50.26, 18.86),   # Ruda Śląska (deszczomierz na oczyszczalni między pompowniami)
    "RY": (50.08, 18.52),   # Rybnik: Zamysłów / Niedobczyce
}

# Kalendarz szkolny – województwo śląskie (2025 i 2026 sprawdzone w komunikatach MEN, reszta do weryfikacji)
FERIE_ZIMOWE = [("2023-01-16", "2023-01-29"), ("2024-01-29", "2024-02-11"), ("2025-02-17", "2025-03-02"),
                ("2026-02-16", "2026-03-01"), ("2027-01-18", "2027-01-31")]
WAKACJE = [("2023-06-24", "2023-08-31"), ("2024-06-22", "2024-08-31"), ("2025-06-28", "2025-08-31"),
           ("2026-06-27", "2026-08-31"), ("2027-06-26", "2027-08-31")]
PRZERWY_SWIATECZNE = [("2023-04-06", "2023-04-11"), ("2023-12-23", "2023-12-31"),
                      ("2024-03-28", "2024-04-02"), ("2024-12-23", "2024-12-31"),
                      ("2025-04-17", "2025-04-22"), ("2025-12-22", "2025-12-31"),
                      ("2026-04-02", "2026-04-07"), ("2026-12-23", "2026-12-31")]
