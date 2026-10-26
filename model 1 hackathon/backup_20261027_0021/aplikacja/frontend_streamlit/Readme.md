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