# Aplikacja – prognoza zużycia energii pompowni ścieków

Aplikacja w przeglądarce (Streamlit) zbudowana na **Detektorze Anomalii GUS**
([github.com/KamiLMusiol/anomaly_deteciton_GUS](https://github.com/KamiLMusiol/anomaly_deteciton_GUS)).
Interfejs, style, panel boczny, zakładki Dane / Wykresy – jak w oryginale. **Na razie aplikacja skupia się na predykcji:**

| Zakładka | Co pokazuje |
|---|---|
| **Twoja prognoza** | **widok dla klienta**: wgraj plik → „Przygotuj prognozę” → kafelki (ile energii jutro, szczyt, średni błąd w % i kWh, porównanie z „jak wczoraj”), opis prostym językiem liczony w Pythonie (bez LLM), wykresy, tabela dzień po dniu, **Excel i CSV do pobrania**. Sama włącza uczciwe sprawdzenie, gdy plik obejmuje okres z treningu |
| Dane, Wykresy | eksploracja danych (z oryginału) – tabela `baza_dobowo` i wgrane pliki |
| **Wyniki modeli** | porównanie wariantów, model vs proste reguły per pompownia, doby suche/mokre, ważność cech, test vs rzeczywistość (`wyniki/` po `python main.py model`) |
| **Prognoza (szczegóły)** | zapisany model (`modele/`): trening, plik CSV (licznik / raport / czas;kwh), backtest, porównanie z regułami, prognoza 24 h |
| **Raport** | na górze podsumowanie dla klienta (jak w „Twoja prognoza”), niżej raport opisowy przez lokalny LLM – fakty liczone w Pythonie (`backend_ml_llm/raport_prognozy.py`), jak w GUS |
| **Pytanie** | pytania o model i prognozę – ten sam kontekst faktów |
| **Jak czytać wyniki** | WAPE, bias, backtest i uczciwy backtest, formaty plików |

Baza po ETL wczytuje się **sama** przy otwarciu aplikacji (przycisk „Wczytaj z bazy” w panelu odświeża).

Zakładki anomalii (Detekcja, Anomalie – nasz potok z `anomalie/`) są **schowane, nie usunięte**:
`$env:POKAZ_ANOMALIE = "1"` przed `python main.py aplikacja` albo `POKAZ_ANOMALIE = True` w `app.py`.

```powershell
python main.py aplikacja            # z głównego folderu projektu  ->  http://localhost:8501
docker compose up aplikacja         # albo w Dockerze (baza startuje sama)
```

## Skąd dane

- **Baza (po ETL)** – przycisk „Wczytaj z bazy” w panelu bocznym: wszystkie pompownie, tabele godzinowe i alarmy CH.
  Do zakładek Dane / Wykresy trafia tabela `baza_dobowo` (kWh i m³ na dobę per pompownia).
- **CSV godzinowy** – wgrany w panelu bocznym: `czas, kwh` + opcjonalnie `obiekt_id, m3, opad_mm, temp_c`.

## Co zmieniono względem Detektora GUS

| Plik | Zmiana |
|---|---|
| `backend_ml_llm/nasz_detektor.py` | **nowy** – adapter: uruchamia nasz potok i zwraca wynik z kolumnami jak `anomaly_d.py` (`Anomaly_IF/_LOF/_SVM/_Votes/_Final`, `{kol}_zscore`, `{kol}_diff_from_rolling_mean`, `{kol}_is_outlier`, `Has_Outlier`, `Nagla_Zmiana`, `Odstaje_Od_Innych`, `Rodzaj_Anomalii`) – dzięki temu Raport i Pytanie działają bez zmian |
| `frontend_streamlit/zakladka_detekcja.py` | przepisana: źródło danych, okno panelowe, dobór odsetka na alarmach CH, walidacja, typ i rodzaj anomalii |
| `frontend_streamlit/zakladka_anomalie.py` | przepisana: oś czasu pompowni (rzeczywiste vs baza bezdeszczowa, opad, anomalie wg typu), typy, ranking wód obcych, główne przyczyny; z oryginału: głosy modeli, szeregi wg jednostek, z-score |
| `frontend_streamlit/wykresy.py` | dopisane 6 wykresów (`fig_os_czasu`, `fig_ranking`, `fig_przyczyny`, `fig_typy`, `fig_prognoza_24h`, `fig_prognoza_dobowa`); `use_container_width` → `width="stretch"` (wycofywane w Streamlit) |
| `frontend_streamlit/panel_boczny.py` | dopisany przycisk „Wczytaj z bazy” |
| `frontend_streamlit/narzedzia.py`, `backend_ml_llm/mistral_raport_generator.py` | adres Ollamy z `OLLAMA_URL` (Docker); w faktach dla LLM dochodzi gotowy opis anomalii z naszego potoku |
| `frontend_streamlit/zakladka_prognoza.py` | **nowa** zakładka: trening modelu, plik CSV (licznik / raport / czas;kwh), backtest, prognoza 24 h, uczciwy backtest |
| `frontend_streamlit/zakladka_twoja_prognoza.py`, `backend_ml_llm/podsumowanie_klienta.py` | **nowe** – widok dla klienta: podsumowanie liczone i pisane w Pythonie, Excel (5 arkuszy) |
| `frontend_streamlit/zakladka_wyniki_modeli.py`, `zakladka_raport_prognozy.py`, `zakladka_pytanie_prognozy.py`, `zakladka_jak_czytac.py` | **nowe** zakładki pod predykcję |
| `backend_ml_llm/raport_prognozy.py` | **nowy** – fakty o prognozie (model, test, ostatnia prognoza) + prompty raportu i pytań (wzór: `report_generator`) |
| `app.py` | ścieżka do projektu, tytuł, zestaw zakładek pod predykcję, przełącznik `POKAZ_ANOMALIE` |
| `frontend_streamlit/panel_boczny.py` | tytuł „Prognoza energii”, przycisk „Wczytaj z bazy” |

Bez zmian: `styles.py`, `pola.py`, `magazyn_danych.py`, `zakladka_dane.py`, `zakladka_wykresy.py`, `zakladka_raport.py`,
`zakladka_pytanie.py`, `zakladka_pomoc.py`, `visualization.py`, `desktop.py`, `.streamlit/config.toml`
(oryginalne Raport / Pytanie / Dobre praktyki zostają w plikach – używane przy włączonych anomaliach).

Raport i Pytanie wymagają Ollamy (`ollama pull qwen3:8b`); bez niej reszta aplikacji działa normalnie.
