# testy/ – testy automatyczne

```powershell
python -m pytest testy -q          # 30 testów, ~10 min, BEZ bazy (dane syntetyczne)
python -m pytest testy -q -k prognoza      # tylko wybrane
```
Dane syntetyczne (`syntetyczne.py`) mają strukturę jak baza po ETL: rytm dobowy, dni wolne, sezon, reakcję na deszcz
i szum. Wyniki trafiają do folderu tymczasowego – testy nie ruszają `wyniki\` ani `modele\`.

| Plik | Co sprawdza |
|---|---|
| `test_czas_i_liczniki.py` | jesienna zmiana czasu w kolejności z pliku, wiosenna brakująca godzina, wiersz 200%, licznik: zera, spadki, reset, przerwa |
| `test_model.py` | **brak podglądania przyszłości** dla horyzontu 1, 3 i 7 dni (zmiana zużycia po chwili prognozy nie zmienia żadnej cechy), XGBoost lepszy od naiwnego |
| `test_prognoza.py` | trening i zapis modelu, **trzy formaty pliku dają ten sam wynik**, backtest lepszy od „jak wczoraj”, prognoza 24 h, za krótka historia, ostrzeżenie o danych z treningu, uczciwy backtest |
| `test_anomalie.py` | zespół łapie wstrzyknięte awarie i dopływy bez deszczu, typy, opis, dobór odsetka po lifcie |
| `test_panel_i_raport.py` | „odstaje od innych” przy 4 obiektach, „nagła zmiana”, raport z Ollamą i bez |
| `test_strojenie.py` | walidacja krocząca nie dotyka testu, zapis parametrów Optuny, ich użycie przy treningu |
| `test_horyzont.py` | modele na K dni lepsze od „jak K dni temu”, prognoza 7 dni ograniczona do wytrenowanych modeli, plan 2 miesiące: lepszy od „średniej z 4 tygodni”, przedział ~80%, sumy tygodni i miesięcy, aplikacja z wyborem horyzontu |
| `test_raport_excel.py` | Excel jako dane do prognozy (4 warianty arkusza, zgodna suma), raport Excel: arkusze, ≥ 9 wykresów, formuły bez funkcji niedostępnych w starszym Excelu |
| `test_wody_przypadkowe.py` | ranking pompowni, zdarzenia (dzień, godziny, objętość, koszt), eksport Excel, komenda `zdarzenia` |
| `test_aplikacja.py` | aplikacja naprawdę uruchomiona (Streamlit AppTest): start, **wgranie plików w panelu**, wykrycie pompowni, Prognoza (podsumowanie, Excel), szczegóły, Model, Raport z atrapą LLM, anomalie z przełącznikiem |
| `conftest.py`, `syntetyczne.py` | wspólne ustawienia i generator danych |

Ostrzeżenia `DeprecationWarning` / `FutureWarning` z bibliotek nie są błędami.
