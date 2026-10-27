# anomalie/ – wykrywanie anomalii

**Status:** gotowe i przetestowane, ale **w aplikacji schowane** (projekt skupia się teraz na prognozie).
Włączenie zakładek: `$env:POKAZ_ANOMALIE = "1"` przed `python main.py aplikacja`. Z konsoli działa zawsze:
```powershell
python main.py anomalie          # → wyniki\anomalie\, tabela anomalie_dni w bazie
python main.py raport            # raport słowny (Ollama; bez niej – same fakty)
```

## Pliki

| Plik | Za co odpowiada |
|---|---|
| `ustawienia.py` | odsetki do sprawdzenia, okno suchości, godziny nocne, okno panelowe, kategorie alarmów CH, znane zdarzenia, model LLM |
| `cechy_dobowe.py` | cechy dobowe: baza bezdeszczowa, nadwyżki, przepływ nocny, **residual prognozy energii (out-of-fold)**, kWh/m³, nastawy pomp |
| `panel.py` | tryb panelowy jak w Detektorze GUS: `jump_score`, `zscore_wlasny`, `zscore_miedzy`, `Rodzaj_Anomalii` |
| `detekcja.py` | **zespół Isolation Forest + LOF + One-Class SVM (≥ 2 z 3)**, główna przyczyna, typ, opis |
| `ocena_anomalii.py` | walidacja na alarmach CH, znane zdarzenia, ranking wód obcych, przyczyny, wykresy |
| `uruchom.py` | całość + dobór odsetka (najwyższy lift przy ≥ 30% złapanych alarmów) |
| `raport.py` | raport słowny: fakty w Pythonie, model językowy tylko formułuje |

Wyniki na prawdziwych danych: odsetek 5%, 145 anomalii (~4% dób), **lift 2,6× na alarmach CH**, powódź IX 2024
wykryta na 4/4 pompowniach jako dopływ opadowy, PNB1 – wysoki przepływ nocny (infiltracja).

## Szczegóły

```powershell
python main.py anomalie
```
Wyniki w `wyniki/anomalie/`, tabela `anomalie_dni` w bazie, podgląd w `anomalie.ipynb`.

## Jak działa

1. **Cechy dobowe** (`anomalie/cechy_dobowe.py`) dla każdego obiektu:
   - **baza bezdeszczowa** (dry weather flow): mediana per dzień tygodnia × godzina z godzin bez opadu przez 72 h,
   - nadwyżka przepływu ponad bazę [%], udział przepływu nocnego 02–05 (wysoki = infiltracja),
   - **residual energii**: rzeczywiste − prognoza XGBoost liczona **out-of-fold** (czas obiektu dzielony na 5 bloków,
     każdy prognozuje model uczony na pozostałych) – z pogodą zmierzoną, więc residual = zużycie, którego pogoda nie tłumaczy,
   - kWh/m³ względem typowego (sprawność pomp), praca pomp (RU), opad doby i 3 dni, temperatura, roztopy.
   Cechy z pokryciem < 60% dób obiektu są pomijane (np. przepływ RY_PZ1 tylko za 2024 → PZ1 oceniany po energii).
2. **Zespół trzech modeli** (`anomalie/detekcja.py`), osobno dla każdego obiektu, cechy skalowane medianą/IQR:
   Isolation Forest, Local Outlier Factor, One-Class SVM. **Anomalia = ≥ 2 z 3 głosów.**
   Opad jest w cechach celowo: dużo wody przy ulewie to norma, dużo wody bez deszczu – anomalia.
3. **Typ anomalii** (reguły): dopływ opadowy · roztopy · infiltracja / dopływ bez deszczu · nadmiar bez deszczu ·
   spadek – awaria / przerwa · spadek sprawności pomp · **zmiana nastaw sterowania** (progi start/stop z SCADA inne niż
   zwykle, np. RU_ZMP 2026) · **spiętrzenie w zbiorniku** (poziom wyraźnie wyżej niż zwykle) · inne.
3a. **Tryb panelowy** (`anomalie/panel.py`, na wzór Detektora Anomalii GUS): jednostka = pompownia, okres = doba.
   `{cecha}_jump_score` – nagła zmiana względem poprzednich 14 dób obiektu, `{cecha}_zscore_wlasny` – na tle własnej historii,
   `{cecha}_zscore_miedzy` – odstawanie od pozostałych pompowni tego samego dnia, `{cecha}_is_outlier` + `Has_Outlier` (IQR).
   `Rodzaj_Anomalii`: nagła zmiana / odstaje od innych / oba / brak wyraźnego wzorca. Zmiany względem GUS:
   okno kroczące bez bieżącego dnia (skok nie „rozmywa” sam siebie) i `zscore_miedzy` liczony jako odchylenie od **mediany
   pozostałych** obiektów skalowane własną typową różnicą – klasyczny z-score przekroju przy n jednostkach nie przekracza
   (n−1)/√n (przy 4 pompowniach 1,5), więc próg 2,0 byłby nieosiągalny.
3b. **Główna przyczyna** = cecha „skutku” (woda, energia, pompy) z największym odpornym |z-score| – jak `build_row_facts` w GUS;
   pogoda jest kontekstem. Do tego **opis** jednym zdaniem: typ, przyczyna, różnica od średniej z 14 dób, skala, opad,
   które modele zagłosowały, rodzaj.
4. **Dobór odsetka anomalii** (2 / 3 / 5 / 8 / 10 / 12%) na alarmach tłoczni CH (spiętrzenia, awarie pomp, zasilanie), tolerancja ±1 doba;
   wybierany **najwyższy lift** zespołu (ile razy częściej niż losowo wskazuje doby przy alarmach) spośród odsetków,
   które łapią ≥ 30% dni z alarmem (remis → mniejszy odsetek).

## Wyniki (`wyniki/anomalie/`)

| Plik | Zawartość |
|---|---|
| `walidacja_CH.csv` | każdy model i zespół × odsetek: złapane alarmy [%], trafienia [%], lift vs losowo |
| `dni.csv` | wszystkie doby: cechy, głosy IF/LOF/SVM, anomalia, typ, skala |
| `anomalie.csv` | tylko doby z anomalią |
| `ranking.csv`, `ranking.png` | per obiekt: udział wód obcych [%], m³ na 1 mm deszczu, przepływ nocny, liczba anomalii wg typu |
| `znane_zdarzenia.csv` | czy wykryto powódź IX 2024 i przeciążenie RU_W I 2024 |
| `anomalie_<obiekt>.png` | oś czasu: rzeczywiste vs baza, anomalie wg typu, opad (CH: alarmy) |

| `przyczyny.csv`, `przyczyny.png` | co najczęściej było główną przyczyną i na ile cecha odróżnia anomalie od zwykłych dób |
| `raport.md` | raport słowny dla dyspozytora (`python main.py raport`) |

## Raport słowny (opcjonalnie, Ollama)

Na wzór `report_generator` z Detektora Anomalii: **wszystkie liczby liczy Python**, lokalny model językowy dostaje gotowe
fakty i ma je tylko sformułować (zakaz zmiany liczb i dodawania faktów). Działa offline.

```powershell
# raz: zainstaluj Ollamę (ollama.com), potem
ollama pull qwen3:8b
python main.py raport                     # albo: --model mistral --top 5
```
Bez Ollamy raport też powstaje – jako uporządkowane fakty. W Dockerze aplikacja łączy się z Ollamą na komputerze
(`OLLAMA_URL=http://host.docker.internal:11434`).

Ustawienia (odsetki, okno suchości, godziny nocne, okno panelowe, kategorie alarmów, znane zdarzenia, model LLM):
`anomalie/ustawienia.py`.