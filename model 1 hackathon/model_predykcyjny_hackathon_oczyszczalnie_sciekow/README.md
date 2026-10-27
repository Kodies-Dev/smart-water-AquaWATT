# Model predykcyjny – hackathon oczyszczalnie ścieków

**Smart Water Challenge 2026** · prognoza zużycia energii pompowni ścieków na następną dobę.

Program zamienia surowe pliki z pompowni (liczniki, raporty dystrybutora, SCADA) w czyste dane, uczy model
XGBoost z prognozą pogody i udostępnia wszystko w aplikacji w przeglądarce: wgrywasz plik z zużyciem energii,
dostajesz **prognozę na kolejną dobę**, **sprawdzenie, jak dokładne byłyby prognozy** w okresie z pliku,
opis prostym językiem i Excel do pobrania.

```
Dane/ ──► ETL ──► Postgres ──► model (XGBoost + pogoda) ──► aplikacja: plik → prognoza 24 h + ocena + Excel
```

**Najważniejsze wyniki** (uczciwy test – model nie znał sprawdzanych dni):

| | Wynik |
|---|---|
| średni błąd dobowy, wszystkie pompownie | **13,9%** (proste metody: 16,8–23,9%) |
| RY_PZ1, cały rok X.2024–IX.2025 | **8,6%** – o 6–35% lepiej niż proste metody |
| doby suche / z deszczem | 7,0% / 24,0% – błąd siedzi w dniach z ulewą |
| model uczony bez Rybnika, test na Rybniku | 8,3% (PZ1) – przenosi się na nowe pompownie |

---

## Spis treści

1. [Co jest w środku](#1-co-jest-w-środku)
2. [Wymagania](#2-wymagania)
3. [Krok po kroku: pobranie, przygotowanie, uruchomienie](#3-krok-po-kroku)
4. [Pierwsze użycie aplikacji](#4-pierwsze-użycie-aplikacji)
5. [Kolejne uruchomienia](#5-kolejne-uruchomienia)
6. [Wszystkie komendy](#6-wszystkie-komendy)
7. [Najczęstsze problemy](#7-najczęstsze-problemy)
8. [Dokumentacja folderów](#8-dokumentacja-folderów)

---

## 1. Co jest w środku

```
model_predykcyjny_hackathon_oczyszczalnie_sciekow/
├── main.py                   punkt wejścia: etl | model | prognoza | anomalie | raport | aplikacja | wszystko
├── Dane/                     surowe pliki od organizatorów (CH, RU, RY) – nie ma ich w repozytorium
├── etl/                      ETL: surowe pliki + pogoda + kalendarz → tabele godzinowe w Postgresie   → etl/README.md
├── sql/                      schemat bazy i widok v_model                                              → sql/README.md
├── model/                    cechy, warianty modeli, ocena, tryb prognozy (model gotowy do pracy)      → model/README.md
├── anomalie/                 wykrywanie anomalii (zespół IF + LOF + One-Class SVM) – w aplikacji schowane → anomalie/README.md
├── aplikacja/                aplikacja Streamlit na bazie Detektora Anomalii GUS                       → aplikacja/README.md
├── testy/                    testy automatyczne (python -m pytest testy)                               → testy/README.md
├── docs/                     opis ETL (Word), przykładowy raport Excel z wykresami (dane syntetyczne)
├── testowe_csv.py            generator plików testowych z prawdziwych danych
├── *.ipynb                   notebooki: sprawdz_baze, wyniki_modeli, anomalie, porownanie
├── DZIEN_KONKURSU.md         ściągawka na dzień konkursu
├── PREZENTACJA.md            jak przygotować prezentację (slajdy, liczby, demo, pytania jury)
├── docker-compose.yml, Dockerfile, requirements.txt, .gitignore
```

Tworzą się same (nie ma ich w repozytorium): `.venv/`, `cache/` (pobrana pogoda), `wyniki/` (wyniki modeli),
`modele/` (wytrenowany model).

---

## 2. Wymagania

| Co | Wersja / uwagi |
|---|---|
| system | Windows 10/11 (opisane komendy PowerShell); macOS / Linux też działa |
| **Python** | 3.12 lub nowszy (sprawdzone na 3.12 i 3.14) |
| **Docker Desktop** | do bazy Postgres (kontener `postgres:16`) |
| internet | przy pierwszym ETL (pogoda Open-Meteo) i dla prognozy na jutro; potem ETL działa z `cache/` |
| miejsce | ok. 3 GB (dane + baza + biblioteki) |
| opcjonalnie: **Ollama** | lokalny model językowy do zakładek Raport i Pytanie (`ollama pull qwen3:8b`) |
| folder `Dane` | pliki od organizatorów: `Dane\CH`, `Dane\RU`, `Dane\RY` |

---

## 3. Krok po kroku

Wszystkie komendy w **PowerShellu** (albo terminalu PyCharma).

### Krok 1. Pobierz program

**Z GitHuba:**
```powershell
cd "C:\Users\<ty>\Desktop"
git clone <adres-repozytorium> model_predykcyjny_hackathon_oczyszczalnie_sciekow
cd model_predykcyjny_hackathon_oczyszczalnie_sciekow
```

**Albo z zipa:** rozpakuj `model_predykcyjny_hackathon_oczyszczalnie_sciekow.zip` tak, żeby powstał folder
`...\model_predykcyjny_hackathon_oczyszczalnie_sciekow\` z `main.py` w środku (przy „Wyodrębnij wszystkie” wskaż
folder **nadrzędny**, bo zip ma już folder programu w środku).

### Krok 2. Dołóż dane

Skopiuj folder **`Dane`** od organizatorów do folderu programu:
```
model_predykcyjny_hackathon_oczyszczalnie_sciekow\Dane\CH\...
model_predykcyjny_hackathon_oczyszczalnie_sciekow\Dane\RU\...
model_predykcyjny_hackathon_oczyszczalnie_sciekow\Dane\RY\...
```

### Krok 3. Środowisko Pythona (raz)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1                         # na początku linii pojawi się (.venv)
python -m pip install -r requirements.txt
```
Jeśli PowerShell blokuje skrypty: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, potem jeszcze raz
`Activate.ps1`. W PyCharmie: *Settings → Project → Python Interpreter → Add → Existing → `.venv\Scripts\python.exe`*.

Polskie znaki w konsoli (warto dodać przy każdym nowym oknie):
```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $env:PYTHONIOENCODING = "utf-8"
```

### Krok 4. Baza danych

Uruchom **Docker Desktop**, potem:
```powershell
docker compose up -d db
docker compose ps                                  # db: healthy, port 0.0.0.0:5435->5432
```
Baza jest na porcie **5435** (żeby nie kolidować z lokalnie zainstalowanym PostgreSQL). Dane w bazie zostają
między uruchomieniami.

### Krok 5. ETL – dane do bazy (~2 min)

```powershell
python main.py etl 2>&1 | Tee-Object log_etl.txt
```
Sprawdź w logu: żadnego `BŁĄD`; kontrola faktur – 3 spodziewane różnice (01.2024 PZ1 i PNB1, 07.2025 PZ1);
korelacja opadu ERA5 ≈ 0,79, prognozy ≈ 0,68.

### Krok 6. Modele

```powershell
python main.py model                               # porównanie wariantów → wyniki\ (zakładka Model)          ~2 min
python main.py strojenie                           # Optuna, walidacja krocząca (opcjonalnie)                 ~15–20 min
python main.py prognoza --trenuj --dni 7           # modele do pracy: 1–7 dni + plan na 2 miesiące → modele\   ~10–15 min
python main.py horyzont                            # dokładność prognozy na 1–7 dni (test) → wyniki\           ~3 min
python main.py horyzont --dlugi                    # dokładność planu na 2 miesiące (test) → wyniki\           ~1 min
```
Oczekiwane: `xgb_prognoza_pogody` ≈ **13,9%** WAPE dobowego na jutro; błąd rośnie z liczbą dni naprzód.
Strojenie przed treningiem: model do pracy użyje dostrojonych parametrów tylko, jeśli wygrały na teście (≥ 0,1 pp).
Sam model na jutro (szybko): `python main.py prognoza --trenuj`.

### Krok 7. Pliki testowe i testy (opcjonalnie, ale warto)

```powershell
python testowe_csv.py                              # Dane\testowe\*.csv + OPIS.md
python -m pytest testy -q                          # 30 passed (~10 min)
```

### Krok 8. Aplikacja

```powershell
python main.py aplikacja                           # otwórz http://localhost:8501
```
Zatrzymanie: `Ctrl+C` w terminalu. Ręcznie (to samo): `cd aplikacja; streamlit run app.py`.

**Skrót kroków 5–6:** `python main.py wszystko` (ETL + modele + anomalie + raport), potem `python main.py prognoza --trenuj`.

---

## 4. Pierwsze użycie aplikacji

1. **Panel po lewej → „Wgraj pliki CSV lub Excel”** → np. `Dane\testowe\01_PZ1_8tyg_licznik_mock.csv` →
   (separator i kodowanie: `automatycznie`) → **Wczytaj pliki**.
   Pojawi się: *„…: 1345 godzin · dane do prognozy (licznik)”*, a niżej **„Której pompowni dotyczą dane do
   prognozy?” → RY_PZ1** (wykryte z nazwy, można zmienić).
2. **Dane** – podgląd, statystyki, porównanie, łączenie, tabela przestawna, SQL (jak w Detektorze GUS).
3. **Wykresy** – liniowy, histogram, boxplot, korelacje.
4. **Wody przypadkowe** – ranking pompowni (infiltracja, dopływ opadowy, energia i koszt), zdarzenia (dzień, godziny, objętość).
   **Anomalie** → **Wykryj anomalie** (dane z panelu albo cała historia pompowni) → zdarzenia + nietypowe doby ML, opis, Excel;
   **Anomalie – szczegóły** – metoda, głosowanie modeli, walidacja.
5. **Prognoza** – kafelki o danych → **Na ile do przodu**: *Jutro (24 h)* · *Tydzień (7 dni)* · *2 miesiące (plan)* →
   **Przygotuj prognozę** (1–2 min: plik był w treningu, więc model uczy się od nowa bez tego okresu) → prognoza,
   średni błąd, porównanie z „jak wczoraj”, opis, wykresy, **Excel**. Tydzień: każdy dzień osobnym modelem.
   2 miesiące: plan dobowy z przedziałem P10–P90 (80% dni) – do budżetu i zakupu energii.
5. **Prognoza – szczegóły** – na podstawie czego powstała prognoza: zużycie na tle deszczu i temperatury,
   prognoza pogody sprzed doby, kalendarz, porównanie z prostymi metodami, dane wejściowe do pobrania.
6. **Model** – jak dobry jest model ogólnie; na dole: zapisany model, trening, odświeżenie bazy.
7. **Raport / Pytanie** – podsumowanie + raport lokalnego LLM (Ollama, opcjonalnie).
8. **Dobre praktyki** – jak przygotować plik, jak czytać wyniki.

Opis wszystkich plików testowych: `Dane\testowe\OPIS.md`.

---

## 5. Kolejne uruchomienia

```powershell
cd "...\model_predykcyjny_hackathon_oczyszczalnie_sciekow"
.venv\Scripts\Activate.ps1
docker compose up -d db
python main.py aplikacja
```
ETL i trening powtarzasz tylko, gdy zmienią się dane (`python main.py etl`, `python main.py prognoza --trenuj`).

---

## 6. Wszystkie komendy

| Komenda | Co robi |
|---|---|
| `python main.py etl` | surowe pliki z `Dane\` → baza (patrz `etl/README.md`) |
| `python main.py model [--warianty a,b]` | porównanie wariantów modeli → `wyniki\` (patrz `model/README.md`) |
| `python main.py strojenie [--proby 30] [--minuty 20]` | Optuna z walidacją kroczącą; test otwierany raz, na końcu |
| `python main.py prognoza --trenuj [--dni 7]` | trening modelu do pracy na wszystkich danych → `modele\` (z `--dni 7`: modele 1–7 dni i plan 2 miesiące) |
| `python main.py horyzont [--dlugi]` | dokładność prognozy na 1–7 dni / planu 2-miesięcznego na teście |
| `python main.py prognoza --plik X.csv [--obiekt RY_PZ1] [--uczciwie] [--dni 7]` | prognoza z pliku w konsoli (bez aplikacji) |
| `python main.py anomalie` / `raport` | wykrywanie anomalii / raport słowny (patrz `anomalie/README.md`) |
| `python main.py zdarzenia [--cena 1]` | **wody przypadkowe: zdarzenia (dzień, godziny, objętość, koszt) + ranking pompowni → `wyniki\`** |
| `python main.py aplikacja` | aplikacja w przeglądarce |
| `python main.py wszystko` | ETL + model + anomalie + raport |
| `python testowe_csv.py` | pliki testowe w `Dane\testowe\` |
| `python -m pytest testy -q` | testy automatyczne |

**Docker zamiast venva** (wszystko w kontenerach):
```powershell
docker compose build
docker compose run --rm app wszystko               # ETL + modele + anomalie + raport
docker compose run --rm app prognoza --trenuj
docker compose up aplikacja                        # http://localhost:8501
```

---

## 7. Najczęstsze problemy

| Objaw | Rozwiązanie |
|---|---|
| `UnicodeDecodeError` przy połączeniu z bazą | działa lokalny PostgreSQL (usługa `postgresql-x64-*`) – baza projektu jest na porcie **5435**; sprawdź `docker compose ps` |
| `Nie ma danych w: ...\Dane` | folder `Dane` musi być w folderze programu (albo ustaw `$env:DANE_DIR`) |
| w pomocy `main.py` nie ma `prognoza` / `aplikacja` | stara wersja – rozpakuj najnowszy zip |
| aplikacja: „Brak połączenia z bazą” | `docker compose up -d db` i odśwież stronę |
| „Brak wytrenowanego modelu” | `python main.py prognoza --trenuj` albo przycisk w zakładce Model |
| „Za mało danych” | plik + historia z bazy < 5 tygodni – wybierz pompownię z bazy albo dłuższy plik |
| plik nie rozpoznany jako dane do prognozy | ustaw separator / kodowanie ręcznie albo przygotuj dwie kolumny `czas;kwh` |
| polskie znaki jako krzaki w konsoli | `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` |
| Raport / Pytanie: „Nie wykryto Ollamy” | `ollama serve`, `ollama pull qwen3:8b` – reszta aplikacji działa bez tego |
| brak internetu | ETL bierze pogodę z `cache\`; prognoza: odznacz „Pobierz aktualną prognozę pogody” |

---

## 8. Dokumentacja folderów

| README | O czym |
|---|---|
| [`etl/README.md`](etl/README.md) | źródła danych, tabele, czas i zmiana czasu, czyszczenie, kontrole jakości |
| [`sql/README.md`](sql/README.md) | schemat bazy, widok `v_model` |
| [`model/README.md`](model/README.md) | cechy, warianty, ocena, wyniki, tryb prognozy, formaty plików, uczciwy backtest |
| [`anomalie/README.md`](anomalie/README.md) | wykrywanie anomalii, tryb panelowy, raport |
| [`aplikacja/README.md`](aplikacja/README.md) | zakładki, przepływ danych, zmiany względem Detektora GUS |
| [`aplikacja/backend_ml_llm/README.md`](aplikacja/backend_ml_llm/README.md) | adaptery, podsumowanie dla klienta, LLM |
| [`aplikacja/frontend_streamlit/Readme.md`](aplikacja/frontend_streamlit/Readme.md) | moduły interfejsu |
| [`testy/README.md`](testy/README.md) | co sprawdza każdy test |
| [`DZIEN_KONKURSU.md`](DZIEN_KONKURSU.md) | ściągawka na konkurs |
| [`PREZENTACJA.md`](PREZENTACJA.md) | przygotowanie prezentacji |
