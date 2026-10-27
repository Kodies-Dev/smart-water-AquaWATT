"""Ustawienia wykrywania anomalii."""
from model.config import WYNIKI as _W, TZ

WYNIKI = _W / "anomalie"

# zespół modeli: anomalia, gdy zgadza się co najmniej MIN_GLOSOW z 3 (Isolation Forest, LOF, One-Class SVM)
MIN_GLOSOW = 2
ODSETKI = [0.02, 0.03, 0.05, 0.08, 0.10, 0.12]   # sprawdzane „oczekiwane odsetki anomalii” – wybór na alarmach CH
ODSETEK_DOMYSLNY = 0.05              # gdy nie ma alarmów do walidacji
MIN_ZLAPANE_PROC = 30                # dobór odsetka: najwyższy lift spośród tych, które łapią >= 30% dni z alarmem

# baza bezdeszczowa: godziny bez opadu przez ostatnie SUCHO_H godzin (suma < SUCHO_MM)
SUCHO_H, SUCHO_MM = 72, 0.5
NOC = (2, 5)                          # godziny nocne (lokalnie) – minimum ścieków bytowych
MIN_GODZIN = 20                       # doba z mniejszą liczbą godzin danych = brak

# prognoza energii do residuali: out-of-fold (każdy blok czasu prognozuje model, który go nie widział)
FOLDY = 5
XGB_OOF = dict(n_estimators=600, learning_rate=0.05, max_depth=6, min_child_weight=10, subsample=0.8,
               colsample_bytree=0.8, tree_method="hist", objective="reg:absoluteerror")

# walidacja na alarmach tłoczni CH (tolerancja ±1 doba)
TOLERANCJA_DNI = 1
ALARMY_KATEGORIE = {
    "spiętrzenie": ["spietrzenie"],
    "awarie pomp": ["awaria_P1", "awaria_P2", "awaria_P3", "brak_wyd_P1", "brak_wyd_P2", "brak_wyd_P3"],
    "zasilanie": ["awaria_zasilania", "praca_agregatu"],
}

# zdarzenia znane z eksploracji – sprawdzamy, czy zostały wykryte
ZNANE_ZDARZENIA = [
    ("powódź IX 2024", ["RU_W", "RU_ZMP", "RY_PNB1", "RY_PZ1"], "2024-09-13", "2024-09-17"),
    ("przeciążenie RU_W I 2024", ["RU_W"], "2024-01-01", "2024-01-03"),
]

# tryb panelowy (jak w Detektorze Anomalii GUS): jednostka = pompownia, okres = doba
OKNO_PANEL = 14              # okno kroczące [doby] do nagłej zmiany (jump_score)
PROG_RODZAJ = 2.0            # |jump_score| lub |zscore_miedzy| powyżej progu = wyraźny wzorzec
MIN_OBIEKTOW_DOBA = 3        # zscore_miedzy liczony, gdy danego dnia są dane z ≥ 3 pompowni
PANEL_BAZA = ["nadwyzka_m3_proc", "residual_proc", "nadwyzka_kwh_proc"]   # porównywalne między obiektami (%)

# raport słowny przez lokalny model językowy (Ollama) – liczby liczone w Pythonie, LLM tylko je formułuje
import os as _os
OLLAMA_URL = _os.environ.get("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = _os.environ.get("LLM_MODEL", "qwen3:8b")
