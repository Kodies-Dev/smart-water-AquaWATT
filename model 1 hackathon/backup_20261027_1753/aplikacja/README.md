# aplikacja/ – prognoza energii w przeglądarce

Aplikacja Streamlit zbudowana na **Detektorze Anomalii GUS**
([github.com/KamiLMusiol/anomaly_deteciton_GUS](https://github.com/KamiLMusiol/anomaly_deteciton_GUS)): ten sam wygląd,
panel boczny, zakładki Dane i Wykresy, generator raportu przez Ollamę. W środku – nasz model prognozy (`model/`).

```powershell
python main.py aplikacja            # z głównego folderu projektu  ->  http://localhost:8501
# albo ręcznie:  cd aplikacja ; streamlit run app.py      (uruchamiać z folderu aplikacja – motyw z .streamlit/)
# albo w Dockerze:  docker compose up aplikacja
```
Wymaga działającej bazy (`docker compose up -d db`) i wytrenowanego modelu (`python main.py prognoza --trenuj`
albo przycisk w zakładce Model). Baza wczytuje się sama przy otwarciu.

## Przepływ

```
panel: Wgraj pliki → Wczytaj pliki ─┬─► zbiory w pamięci ──► Dane, Wykresy (narzędzia z GUS)
                                    └─► pliki z zużyciem energii = dane do prognozy + wybór pompowni
                                                     │
            Prognoza: „Przygotuj prognozę” ◄─────────┘ ──► Prognoza – szczegóły, Raport, Pytanie
```

## Panel boczny (`frontend_streamlit/panel_prognozy.py`)

Jak w Detektorze GUS: **Wgraj pliki CSV lub Excel** (kilka naraz) · wiersz nagłówka (Excel) · separator · kodowanie
(domyślnie `automatycznie`) · **Wczytaj pliki** · **Zbiór aktywny** (Wierszy | Kolumn | Zbiorów w pamięci) ·
maks. punktów na wykresie. Dochodzi jedno: pliki w formacie zużycia energii (licznik jak `mock_*`, raport
dystrybutora, `czas;kwh`, **także Excel**: kolumny czas + kWh pod różnymi nazwami, osobno data i godzina albo odczyty
licznika) są rozpoznawane same i stają się **danymi do prognozy** (kilka plików tej samej pompowni
→ jedna seria), a poniżej: **„Której pompowni dotyczą dane do prognozy?”** (wykrywana z nazwy, do zmiany; „nowa
pompownia” + miasto). Pozostałe pliki ładują się jak w GUS – do podglądu i porównań.

## Zakładki

| # | Zakładka | Plik | Co pokazuje |
|---|---|---|---|
| 1 | **Dane** | `zakladka_dane.py` (GUS, bez zmian) | podgląd, statystyki, porównanie zbiorów, łączenie tabel, nazwy kolumn, tabela przestawna, SQL |
| 2 | **Wykresy** | `zakladka_wykresy.py` (GUS, bez zmian) | liniowy, histogram, boxplot, korelacje |
| 3 | **Prognoza** | `zakladka_twoja_prognoza.py` | **widok dla klienta**: kafelki o danych → „Przygotuj prognozę” → prognoza 24 h, średni błąd (% i kWh), porównanie z „jak wczoraj”, opis prostym językiem (Python, bez LLM), wykresy, dzień po dniu, **Excel i CSV**; sama włącza uczciwe sprawdzenie |
| 4 | **Prognoza – szczegóły** | `zakladka_prognoza_szczegoly.py` | na podstawie czego powstała prognoza; zużycie na tle deszczu (zmierzonego i prognozowanego) i temperatury; jutro z prognozą pogody; porównanie z prostymi metodami; ważność cech; dane wejściowe CSV |
| 5 | **Model** | `zakladka_model.py` + `zakladka_wyniki_modeli.py` | wyniki eksperymentów (warianty, per pompownia, suche/mokre, ważność cech, test vs rzeczywistość); zapisany model, trening, odświeżenie bazy |
| – | **Raport w Excelu (z wykresami)** | `backend_ml_llm/raport_excel.py` | przycisk w Prognozie i Raporcie: Podsumowanie (formuły), Jutro godzinowo, Dzień po dniu, Miesięcznie, Tydzień, Plan 2 miesiące, Pogoda, Raport AI, Godzinowo – natywne wykresy Excela, sumy i błędy liczone formułami |
| 6 | **Raport** | `zakladka_raport_prognozy.py` | podsumowanie dla klienta + raport opisowy lokalnego LLM; wybór modelu Ollamy z pobieraniem (Bielik, qwen3…) |
| 7 | **Pytanie** | `zakladka_pytanie_prognozy.py` | pytania o model i prognozę (LLM na policzonych faktach) |
| 8 | **Dobre praktyki** | `zakladka_jak_czytac.py` | jak przygotować plik, miary błędu, uczciwy backtest, gdzie model się myli |

**Anomalie** (Detekcja, Anomalie – nasz potok z `anomalie/`) są schowane: `$env:POKAZ_ANOMALIE = "1"`.

## Co zmieniono względem Detektora GUS

| Plik | Zmiana |
|---|---|
| `app.py` | ścieżka do projektu, tytuł, automatyczne wczytanie bazy, zestaw zakładek, przełącznik `POKAZ_ANOMALIE` |
| `frontend_streamlit/panel_prognozy.py` | **nowy** panel na wzór `panel_boczny.py` + rozpoznawanie danych do prognozy i wybór pompowni (`panel_boczny.py` zostaje, nieużywany) |
| `frontend_streamlit/zakladka_*` prognozy, modelu, raportu, pytania, dobrych praktyk | **nowe** zakładki pod predykcję |
| `frontend_streamlit/wykresy.py` | dopisane wykresy (oś czasu, wyniki modeli, prognoza, widok klienta); `show(fig, key=None)`; `width="stretch"` |
| `frontend_streamlit/narzedzia.py`, `backend_ml_llm/mistral_raport_generator.py` | adres Ollamy z `OLLAMA_URL`; w faktach dla LLM opis z naszego potoku |
| `backend_ml_llm/` nasz_detektor, raport_prognozy, podsumowanie_klienta | **nowe** – patrz `backend_ml_llm/README.md` |
| `frontend_streamlit/zakladka_detekcja.py`, `zakladka_anomalie.py` | przepisane pod nasz potok anomalii (schowane) |

Bez zmian: `styles.py`, `pola.py`, `magazyn_danych.py`, `zakladka_dane.py`, `zakladka_wykresy.py`, `zakladka_raport.py`,
`zakladka_pytanie.py`, `zakladka_pomoc.py`, `visualization.py`, `desktop.py`, `.streamlit/config.toml`.

## Testy

`testy/test_aplikacja.py` uruchamia aplikację naprawdę (Streamlit AppTest): wgrywa pliki w panelu, klika
„Wczytaj pliki” i „Przygotuj prognozę”, sprawdza zakładki. `python -m pytest testy -q -k aplikacja`.
