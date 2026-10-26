# Model predykcyjny – hackathon oczyszczalnie ścieków

Smart Water Challenge 2026. Jeden program, dwa etapy:

1. **ETL** – surowe pliki z `Dane/` + pogoda + kalendarz → oczyszczone tabele godzinowe w Postgresie,
2. **Model** – prognoza zużycia energii na następną dobę: kilka wariantów modeli porównanych na zbiorze testowym,
3. **Anomalie** – wykrywanie dób z nadmiarem wody / energii (zespół Isolation Forest + LOF + One-Class SVM, ≥ 2 z 3), ich typ,
   rodzaj (nagła zmiana / odstaje od innych pompowni) i raport słowny dla dyspozytora. Podejście przeniesione i dostosowane
   z [Detektora Anomalii (GUS)](https://github.com/KamiLMusiol/anomaly_deteciton_GUS),
4. **Prognoza** – model gotowy do pracy: trening na wszystkich danych, zapis do `modele/`, prognoza z nowego CSV
   (`python main.py prognoza --plik dane.csv`),
5. **Aplikacja** – przeglądarkowa aplikacja Streamlit na bazie Detektora Anomalii GUS, z naszym potokiem anomalii
   (`python main.py aplikacja` → http://localhost:8501).

```
Dane/  ──►  ETL  ──►  Postgres (smartwater)  ──►  modele  ──►  wyniki/
```

## Struktura

```
└── model_predykcyjny_hackathon_oczyszczalnie_sciekow/
    ├── Dane/                   surowe pliki (CH, RU, RY) – tylko do odczytu, nie w zipie
    ├── main.py                 punkt wejścia: etl | model | anomalie | raport | prognoza | aplikacja | wszystko
    ├── docker-compose.yml      baza (postgres:16) + aplikacja
    ├── Dockerfile, requirements.txt
    ├── DZIEN_KONKURSU.md       ściągawka: checklista, komendy na dane finalne, pokaz, liczby na slajdy
    ├── sql/schema.sql          tabele + widok v_model
    ├── etl/                    ETL
    │   ├── config.py           ścieżki, obiekty, punkty pogody, kalendarz szkolny, okresy do odcięcia
    │   ├── wspolne.py          czas lokalny -> UTC, licznik -> godziny, energia godzinowa -> UTC
    │   ├── ch.py  ru.py  ry.py źródła per miasto
    │   ├── zewnetrzne.py       pogoda (Open-Meteo) + kalendarz (święta, ferie, wakacje)
    │   ├── baza.py, main.py    zapis, kolejność kroków, log, kontrole
    ├── model/                  modele
    │   ├── config.py           horyzont, podział 70/30, parametry XGBoost
    │   ├── dane.py, cechy.py   wczytanie z bazy, cechy (te same w treningu i w dniu konkursu)
    │   ├── modele.py, ocena.py baseline'y, Ridge, XGBoost; metryki i wykresy
    │   ├── eksperymenty.py     lista wariantów i porównanie
    │   └── prognoza.py         model gotowy do pracy: trening, zapis, wczytanie CSV, backtest, prognoza 24 h
    ├── anomalie/               wykrywanie anomalii
    │   ├── ustawienia.py       odsetki, okno suchości, godziny nocne, kategorie alarmów, znane zdarzenia
    │   ├── cechy_dobowe.py     baza bezdeszczowa, nadwyżki, przepływ nocny, residual energii (out-of-fold)
    │   ├── panel.py            tryb panelowy (jak w Detektorze GUS): jump_score, zscore_miedzy, Rodzaj_Anomalii
    │   ├── detekcja.py         zespół IF + LOF + One-Class SVM (≥ 2 z 3), główna przyczyna, typ, opis
    │   ├── raport.py           raport słowny (fakty w Pythonie + Ollama)
    │   ├── ocena_anomalii.py   walidacja na alarmach CH, znane zdarzenia, ranking, wykresy
    │   └── uruchom.py          całość
    ├── aplikacja/              aplikacja Streamlit na bazie Detektora Anomalii GUS (opis zmian: aplikacja/README.md)
    ├── modele/                 wytrenowany model (tworzy się sam: python main.py prognoza --trenuj)
    ├── testy/                  testy automatyczne (python -m pytest testy)
    ├── sprawdz_baze.ipynb      podgląd bazy po ETL
    ├── wyniki_modeli.ipynb     jak dobre są modele prognozy (do prezentacji)
    ├── anomalie.ipynb          wyniki anomalii (do prezentacji)
    ├── porownanie.ipynb        porównanie wariantów modeli
    ├── docs/ETL_opis.docx   pełny opis ETL
    ├── cache/                  pobrana pogoda (tworzy się sama)
    └── wyniki/                 wyniki modeli (tworzy się sam)
```

## Uruchomienie – Docker

W folderze programu:

```powershell
docker compose build
docker compose run --rm app wszystko        # ETL + modele
docker compose run --rm app etl             # tylko ETL
docker compose run --rm app model           # tylko modele (baza już załadowana)
docker compose run --rm app anomalie        # tylko anomalie
docker compose run --rm app raport          # raport słowny (Ollama na komputerze, opcjonalnie)
docker compose up aplikacja                 # aplikacja w przeglądarce: http://localhost:8501
docker compose run --rm app model --warianty xgb_opad_przeszly,naiwny_tydzien
```

- Baza startuje sama i zostaje włączona: `127.0.0.1:5435`, baza `smartwater`, `hack` / `hack`
  (port 5435, żeby nie kolidować z lokalnie zainstalowanym PostgreSQL). Połączenie ustawiasz w jednym miejscu: `etl/config.py`.
- Wyniki modeli lądują w `wyniki/` na dysku, pogoda w `cache/`.
- **Pierwszy ETL potrzebuje internetu** (pogoda); kolejne działają z `cache/` także offline.

## Uruchomienie – lokalnie (venv)

```powershell
python -m pip install -r requirements.txt
docker compose up -d db                     # sama baza
python main.py wszystko                     # albo: etl / model
```
Na macOS, jeśli XGBoost zgłosi brak `libomp`: `brew install libomp`.

## Testy

```powershell
python -m pytest testy -q
```
Bez bazy, na danych syntetycznych (~1–2 min). Sprawdzają:
- zmianę czasu (jesienna powtórzona godzina, wiosenna brakująca, wiersz 200%) i liczniki (zera, spadki, reset, przerwa),
- **brak podglądania przyszłości**: zmiana zużycia po chwili prognozy nie może zmienić cech modelu,
- że XGBoost jest lepszy od naiwnej prognozy,
- że zespół anomalii łapie wstrzyknięte zdarzenia (awaria, dopływ bez deszczu) i dobrze je nazywa,
- tryb panelowy: „odstaje od innych” działa przy 4 obiektach, a „nagła zmiana” łapie pierwszy dzień skoku,
- raport: bez Ollamy (same fakty) i z Ollamą (atrapa; usuwanie tokenów `<think>` z qwen3),
- prognoza: trening i zapis modelu, trzy formaty pliku (licznik, raport, czas;kwh) dają ten sam wynik, backtest lepszy
  od prognozy naiwnej, prognoza 24 h, ostrzeżenie o danych z treningu i uczciwy backtest,
- aplikacja: start, detekcja z bazy i z CSV godzinowego, zakładka Prognoza (prawdziwe uruchomienie skryptu Streamlit, kliknięcia),
  kolumny zgodne z Detektorem GUS, fakty dla raportu.

## Najczęstsze problemy

| Objaw | Rozwiązanie |
|---|---|
| port zajęty / lokalny PostgreSQL (np. usługa `postgresql-x64-18`) | baza z Dockera jest na porcie **5435**; zmień w `docker-compose.yml` i `etl/config.py` (`DB_URL`), jeśli trzeba |
| błąd pobierania pogody | brak internetu przy pierwszym uruchomieniu; później ETL bierze kopię z `cache/` |
| krok ETL kończy się `BŁĄD` | pozostałe kroki i tak się wykonują; szczegóły w konsoli i w `etl_log` |

---

# Część 1: ETL

Pełny opis: `docs/ETL_opis.docx`.

## Przebieg

1. **Schemat i obiekty** – tabele (jeśli ich nie ma), wyczyszczenie danych, 5 obiektów z parametrami pomp.
2. **Chorzów** – licznik energii, licznik ścieków, alarmy tłoczni.
3. **Ruda Śląska** – energia W i ZMP, opad z deszczomierza, SCADA (najdłuższy krok).
4. **Rybnik** – raporty godzinowe energii, liczniki przepływu, faktury.
5. **Dane zewnętrzne** – pogoda dla 3 punktów (Open-Meteo, ERA5), **prognoza pogody wydana dzień wcześniej**
   (Open-Meteo Previous Runs, od 01.2024), kalendarz 2023–2027.
6. **Kontrole** – faktury vs raporty godzinowe, opad ERA5 i opad z prognozy vs deszczomierz.
7. **Zapis** – wszystkie tabele + `etl_log`.

Każde uruchomienie ładuje wszystko od zera. Kroki są niezależne – błąd w jednym źródle nie zatrzymuje reszty.

## Tabele

| Tabela | Zawartość |
|---|---|
| `obiekty` | CH_T, RU_W, RU_ZMP, RY_PNB1, RY_PZ1 + parametry pomp + punkt pogody |
| `energia_godz` | kWh na godzinę – **cel prognozy** |
| `energia_mies` | faktury RY (miesięcznie, 2023–2026) |
| `przeplyw_godz` | m³ na godzinę z liczników (CH_T, RU_W, RY_PNB1, RY_PZ1) |
| `scada_godz` | RU: poziom, prądy pomp, pompogodziny, przepływ chwilowy, progi |
| `opad_godz` | opad [mm/h], deszczomierz w Rudzie Śl. |
| `pogoda_godz` | Open-Meteo dla CH, RU, RY: temperatura, opad, deszcz, śnieg, pokrywa śnieżna, wilgotność gleby, parowanie |
| `prognoza_pogody_godz` | prognoza wydana ~24 h wcześniej (Open-Meteo Previous Runs, `_previous_day1`): opad, deszcz, śnieg, temperatura |
| `kalendarz` | weekend, święto (z nazwą), dzień wolny, mostek, ferie / wakacje / przerwy (woj. śląskie) |
| `alarmy` | alarmy tłoczni CH (czas, sygnał, stan 0/1) |
| `etl_log` | wiersze przed / po czyszczeniu w każdym kroku |
| `v_model` | widok: energia + przepływ + SCADA + opad + pogoda + kalendarz w jednej godzinie |

## Obsługa czasu

Wszystkie tabele: **`czas` = początek godziny w UTC**.

- **Liczniki i SCADA** (czas lokalny): jesienią godzina 02:00–03:00 jest dwa razy; pierwsza seria w pliku = czas letni,
  druga (po cofnięciu zegara) = zimowy. ETL rozpoznaje cofnięcie zegara, dlatego **przed konwersją nie wolno sortować**.
- **Energia godzinowa (RU, RY)**: znacznik = koniec godziny → −1 h, potem UTC. Wiosna: godzina nie istnieje (usuwana).
  Jesień: obie godziny w jednym wierszu (RY: kompletność 200%) → dzielone na pół.
- **Opad i pogoda**: już w UTC. **Kalendarz**: daty lokalne.

## Reguły czyszczenia

- liczniki: tylko status `Wartość z pomiaru`, bez zer i duplikatów; spadek > 1% = reset licznika; drobne spadki usuwane
  bieżącym maksimum; przyrost po przerwie > 2 h = brak
- energia godzinowa: 0 kWh = brak danych
- SCADA RU: wiersze z progami = 0 usuwane; godzina z < 60 próbkami = brak
- opad: mm/h ÷ 60 na wiersz (1 min), brak wpisu = 0 mm
- RY PZ1: przepływ przed 01.04.2024 odcięty (rozruch licznika)
- faktury: kontrola z raportami; różnica > 1% wypisywana (spodziewane 01.2024 i 07.2025)

## Kontrola jakości

- **`etl_log`** – % odrzuconych wierszy w każdym kroku (historia uruchomień).
- **Kontrola faktur** – sumy miesięczne raportów RY vs faktury.
- **Kontrola opadu** – korelacja dobowa Open-Meteo z deszczomierzem w Rudzie; ≥ 0,7 uzasadnia Open-Meteo dla CH i RY.
  To samo dla prognozy z dnia poprzedniego – pokazuje, jak trafna była prognoza deszczu.

---

# Część 2: Modele

## Założenia

- **Cel:** kWh na godzinę dla każdego obiektu; prognozy dobowe i miesięczne = suma godzinowa.
- **Horyzont:** następna doba (`H = 24` w `model/config.py`) – model używa tylko tego, co znane 24 h wcześniej.
- **Podział:** chronologicznie, osobno dla każdego obiektu – pierwsze 70% czasu trening, ostatnie 30% test
  (losowy podział „podglądałby przyszłość” przez lagi). Końcówka treningu (15%) = walidacja do early stopping.
- **Normalizacja i cel:** model przewiduje log(1 + kWh / mediana obiektu z ostatnich 28 dni) → jeden model dla wszystkich
  obiektów, odporny na zmiany poziomu i szczyty po ulewach.
- **Strata absolutna** (`reg:absoluteerror`): model celuje w medianę, zgodnie z metryką WAPE. Mediana zaniża sumy
  na obiektach ze szczytami po ulewach (CH, RU_W). Kalibracja mnożnikiem per obiekt została sprawdzona i odrzucona –
  zawyżała doby suche (kod zostaje w `modele.py`, opcja `kalibracja=True`).
- **Okno normalizacji:** domyślnie mediana z 28 dni; warianty `_7d` używają 7 dni (szybciej łapią zmiany poziomu).
  Cecha `poziom_zmiana` (mediana 7 dni / 28 dni) jest we wszystkich wariantach.
- **Wybór per obiekt (`wybor_per_obiekt`):** dla każdego obiektu wariant z najmniejszym WAPE dobowym **na walidacji**
  (nie na teście); na teście tylko sprawdzamy wynik. Uwaga: walidacja służy też do early stopping XGBoosta,
  więc wybór lekko faworyzuje XGBoosty.
- **Prognoza pogody:** warianty `xgb_prognoza_*` używają prognozy wydanej ~24 h wcześniej – to realny scenariusz.
  `xgb_pogoda_rzeczywista` (pogoda zmierzona) to górna granica.

## Warianty

| Wariant | Co sprawdza |
|---|---|
| `naiwny_doba`, `naiwny_tydzien`, `profil_4tyg` | punkty odniesienia: wczoraj / tydzień temu / mediana 4 tygodni |
| `liniowy` | regresja liniowa (Ridge) |
| `xgb_kalendarz_lagi` | XGBoost: kalendarz + historia energii |
| `xgb_opad_przeszly` | + opad do chwili prognozy |
| `xgb_pogoda_przeszla` | + temperatura, śnieg, roztopy, wilgotność gleby, parowanie |
| `xgb_operacyjne` | + przepływ i praca pomp z wczoraj + parametry pomp |
| `xgb_prognoza_pogody` | + **prognoza pogody wydana dzień wcześniej** (opad, śnieg, temperatura) – realny scenariusz |
| `xgb_kalendarz_lagi_7d`, `xgb_operacyjne_7d`, `xgb_prognoza_pogody_7d` | jw., ale normalizacja medianą z 7 dni |
| `xgb_pogoda_rzeczywista` | pogoda w godzinie prognozy = „idealna prognoza pogody” (górna granica) |
| `xgb_per_obiekt` | osobny model dla każdego obiektu |
| `xgb_transfer_RY` | uczony tylko na CH i RU, testowany na Rybniku |
| `xgb_transfer_RY_prognoza` | jw. + prognoza pogody |
| **`wybor_per_obiekt`** | **dla każdego obiektu najlepszy wariant na walidacji** (bez `xgb_pogoda_rzeczywista` i transferów) |

Nowe warianty: słownik `WARIANTY` w `model/eksperymenty.py`; grupy cech w `model/cechy.py`.

## Wyniki (`wyniki/`)

- `metryki.csv` – MAE, RMSE [kWh/h], WAPE godzinowe i dobowe [%], WAPE dobowe osobno dla dób suchych i mokrych
  (opad > 1 mm), bias [%], poprawa vs naiwny tydzień
- `prognozy_test.csv.gz` – prognozy wszystkich wariantów na zbiorze testowym
- `test_<obiekt>.png` – rzeczywistość vs 3 najlepsze warianty
- `waznosc_<wariant>.png/.csv` – ważność cech
- `wybor_per_obiekt.csv` – który wariant wybrano dla którego obiektu i z jakim wynikiem na walidacji

**WAPE** = suma |błędów| / suma zużycia; dobowe liczone tylko z pełnych dób. `RAZEM` zdominowane przez PZ1.

---

## Założenia do weryfikacji

| Założenie | Co sprawdzić |
|---|---|
| nazwy kolumn SCADA RU | potwierdzone fizyką pomp; potwierdzić u organizatorów |
| jednostki m³ i kWh | potwierdzone pośrednio (wydajność pompy CH, zgodność faktur) |
| ZMP = pompownia „T” | pytanie do organizatorów |
| PNB1 = ul. Sztygarska, PZ1 = ul. Dolna | dopasowanie do schematu po adresie i skali przepływu |
| odcięcie przepływu PZ1 przed 01.04.2024 | data przybliżona |
| jesienna godzina RU w jednym wierszu | sprawdzić 27.10.2024 03:00 vs sąsiednie godziny |
| ferie i przerwy 2023–2024, 2027 | 2025 i 2026 sprawdzone, reszta do weryfikacji |
| horyzont prognozy = doba | pytanie do organizatorów |

## Dzień konkursu

- Pliki `mock_*` wskazują format danych finalnych (liczniki `data;godzina;typ;wartosc;status`) – ETL go obsługuje.
- Pogoda działa z `cache/` bez internetu.
- Do zrobienia: wejście dla nowego folderu z danymi finalnymi i prognoza na nich (po informacji od organizatorów).

---

# Część 3: Anomalie

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

---

# Część 4: Prognoza – model gotowy do pracy

```powershell
python main.py prognoza --trenuj                              # raz: trening na WSZYSTKICH danych z bazy -> modele/
python main.py prognoza --plik "Dane\nowe\mock_zuzycie.csv"   # backtest na pliku + prognoza na kolejne 24 h
python main.py prognoza --plik dane.csv --obiekt RY_PZ1 --uczciwie
python main.py prognoza --obiekt RY_PZ1                       # bez pliku: z bazy, prognoza 24 h po ostatniej godzinie
```

- **Model:** `xgb_prognoza_pogody` (najlepszy uczciwy wariant z części 2). Liczba drzew z early stopping na ostatnich
  10% czasu każdego obiektu, potem trening na wszystkich danych. Zapis: `modele/xgb_prognoza_pogody.json` + `_meta.json`.
- **Formaty pliku** (rozpoznawane same): licznik narastający `data;godzina;typ;wartosc;status` (jak `mock_*`, przyrosty
  jak w ETL), raport dystrybutora (jak `Rap_godzinowy_*`, koniec godziny), prosty `czas;kwh [;obiekt_id]`
  (czas lokalny = początek godziny, `--koniec-godziny` gdy koniec).
- **Historia:** model potrzebuje ~5 tygodni wstecz. Jeśli `--obiekt` jest w bazie (np. RY_PZ1), wcześniejsze godziny
  są dociągane z bazy; obiekt spoza bazy musi mieć ≥ 5 tygodni w pliku (działa jak transfer – część 2).
- **Pogoda:** z bazy (ERA5 + prognozy z dnia poprzedniego), ostatnie dni i jutro z bieżącej prognozy Open-Meteo
  (internet; `--bez-pogody-biezacej` wyłącza – wtedy te cechy są puste). `--stacja CH|RU|RY` dla obiektu spoza bazy.
- **Backtest:** każda doba prognozowana „dzień wcześniej” (te same cechy co w części 2), z porównaniem na tych samych
  dobach z prostymi regułami: „wczoraj o tej godzinie”, „tydzień temu”, „mediana z 4 tygodni”. **Uwaga:** zapisany model widział
  w treningu wszystkie dane z bazy – jeśli plik obejmuje ten okres, program to wypisze, a `--uczciwie` trenuje model
  od nowa **bez okresu z pliku** (prawdziwy test na nieznanych danych).
- **Wyniki** (`wyniki/prognoza/`): `<obiekt>_prognoza.csv` (godzinowo: rzeczywiste, prognoza), `<obiekt>_metryki.json`
  (WAPE dobowe i godzinowe, bias, prognoza 24 h), `<obiekt>_prognoza.png`.
- W aplikacji: zakładka **Prognoza** (plik wgrywany w zakładce, te same opcje).

---

# Część 5: Aplikacja w przeglądarce

```powershell
python main.py aplikacja          # -> http://localhost:8501
```
Na bazie [Detektora Anomalii GUS](https://github.com/KamiLMusiol/anomaly_deteciton_GUS) – ten sam interfejs, **skupiony na
predykcji i kliencie**: **Twoja prognoza** (plik → jeden przycisk → opis prostym językiem, wykresy, Excel), **Wyniki modeli**,
**Prognoza (szczegóły)**, **Raport** i **Pytanie** o prognozę (LLM, fakty liczone w Pythonie), Dane, Wykresy, Jak czytać wyniki. Zakładki anomalii są schowane (`$env:POKAZ_ANOMALIE = "1"` – wracają).
1. Baza (po `python main.py etl`) wczytuje się sama.
2. **Twoja prognoza** – plik z danymi albo pompownia z bazy → **Przygotuj prognozę** → wynik dla klienta + Excel.
3. **Wyniki modeli** – jak dobry jest model (po `python main.py model`).
4. **Raport** / **Pytanie** – przez Ollamę (bez niej widać same fakty).

Szczegóły i lista zmian względem GUS: `aplikacja/README.md`.
