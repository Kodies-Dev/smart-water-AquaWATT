# frontend_streamlit

Warstwa interfejsu - wszystko co uzytkownik widzi i klika.

Kazdy plik ma jedna odpowiedzialnosc. Jesli szukasz konkretnej rzeczy do
poprawy, tabela nizej mowi gdzie zajrzec, zeby nie przegladac wszystkiego.

## Moduly wspolne

| Plik | Klasa | Za co odpowiada |
|---|---|---|
| `styles.py` | `Wyglad` | kolory, CSS, wspolny wyglad wykresow, tekst pomocy o z-score |
| `pola.py` | `Pola` | pola liczbowe z przycinaniem wartosci, reczne zakresy osi |
| `narzedzia.py` | `Narzedzia` | eksport CSV, lista modeli z Ollamy, probkowanie wykresow |
| `wykresy.py` | `Wykresy` | wszystkie 9 wykresow Plotly |
| `magazyn_danych.py` | `MagazynDanych` | wczytane zbiory w pamieci sesji, ktory jest aktywny |
| `panel_boczny.py` | - | wgrywanie plikow CSV/Excel, wybor zbioru aktywnego |
| `visualization.py` | `anomaly_visualizer` | wykresy matplotlib **tylko do notatnika**, nieuzywane w aplikacji |

## Zakladki

Kazda ma funkcje `renderuj()` bez argumentow, wolana z `app.py`.

| Plik | Zakladka | Zawartosc |
|---|---|---|
| `zakladka_dane.py` | Dane | podglad, porownanie zbiorow, laczenie, tabela przestawna, SQL |
| `zakladka_wykresy.py` | Wykresy | liniowy, histogram, boxplot, korelacje - surowe dane |
| `zakladka_detekcja.py` | Detekcja | wybor kolumn, tryb, parametry, uruchomienie modeli |
| `zakladka_anomalie.py` | Anomalie | wykresy WYNIKOW detekcji |
| `zakladka_raport.py` | Raport | generowanie opisu przez LLM, partiami |
| `zakladka_pytanie.py` | Pytanie | pytania o zbior wlasnymi slowami |
| `zakladka_pomoc.py` | Dobre praktyki | poradnik, czysty tekst bez logiki |

## Jak dodac nowa zakladke

1. Utworz `zakladka_nazwa.py` z funkcja `renderuj()`
2. W `app.py` dodaj import: `from frontend_streamlit import zakladka_nazwa`
3. Dopisz nazwe do listy w `st.tabs([...])`
4. Dodaj blok `with tab_nazwa: zakladka_nazwa.renderuj()`

Nic wiecej - `build.sh` pakuje caly folder `frontend_streamlit`, wiec nowy plik
trafi do binarki automatycznie, bez zmian w skryptach budujacych.

## Importy

Wszystkie sa **pelne, z prefiksem pakietu**:

```python
from frontend_streamlit.wykresy import Wykresy
from backend_ml_llm.anomaly_d import anomaly_detector
```

Nie skracac do `from wykresy import Wykresy` - zadziala przy
`streamlit run app.py`, ale wysypie sie w wersji spakowanej.

## Gdzie NIE ma kolorow

W plikach zakladek nie ma na sztywno wpisanych kolorow ani stylow. Wszystko
siedzi w `styles.py` (`COL_PRIMARY`, `COL_ANOM`, `PLOT_LAYOUT`, CSS). Chcesz
zmienic wyglad - zmieniasz tam, raz, dla calej aplikacji.

---

## Moduły dodane w projekcie hackathonu (prognoza energii)

Oryginalne moduły powyżej zostają; dochodzą (szczegóły: `aplikacja/README.md`):

| Plik | Zakładka / rola |
|---|---|
| `panel_prognozy.py` | panel boczny na wzór `panel_boczny.py`: wgrywanie plików, zbiór aktywny + rozpoznanie danych do prognozy i wybór pompowni |
| `zakladka_twoja_prognoza.py` | **Prognoza** – widok dla klienta (`pokaz_podsumowanie()` używa też Raport) |
| `zakladka_prognoza_szczegoly.py` | **Prognoza – szczegóły** – dane wejściowe prognozy, pogoda, kalendarz |
| `zakladka_model.py`, `zakladka_wyniki_modeli.py` | **Model** – wyniki eksperymentów, zapisany model, trening |
| `zakladka_raport_prognozy.py`, `zakladka_pytanie_prognozy.py` | **Raport**, **Pytanie** – o prognozie (lista modeli Ollamy z pobieraniem) |
| `zakladka_jak_czytac.py` | **Dobre praktyki** |
| `zakladka_prognoza.py` | stary widok techniczny prognozy (nieużywany w zakładkach; działa z CLI-podobnymi opcjami) |
| `zakladka_detekcja.py`, `zakladka_anomalie.py` | anomalie – przepisane pod nasz potok, schowane (`POKAZ_ANOMALIE=1`) |

W `wykresy.py` dopisane metody (na końcu pliku): oś czasu pompowni, wyniki modeli, prognoza 24 h, trafność dzień po dniu.
