# Dzień konkursu – ściągawka

## Wieczór przed (wtorek) – checklista

```powershell
cd "C:\Users\kam05\Desktop\mdoel 1 hackathon\model_predykcyjny_hackathon_oczyszczalnie_sciekow"
.venv\Scripts\Activate.ps1
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $env:PYTHONIOENCODING = "utf-8"
docker compose up -d db
python -m pytest testy -q                 # 18 passed
python main.py wszystko                   # ETL + modele + anomalie + raport (~6 min) – pobiera pogodę do cache\
python main.py prognoza --trenuj          # model gotowy do pracy -> modele\
ollama pull qwen3:8b                      # tylko jeśli organizatorzy zgodzą się na LLM
python main.py aplikacja                  # sprawdź: Wczytaj z bazy -> Detekcja -> Anomalie -> Prognoza
```
- [ ] baza działa i ma dane (`docker compose ps` → healthy; ETL bez `BŁĄD`)
- [ ] `modele\xgb_prognoza_pogody.json` istnieje
- [ ] `cache\` ma pliki `openmeteo_*.json` (pogoda działa bez internetu)
- [ ] aplikacja otwiera się na http://localhost:8501
- [ ] laptop naładowany, Docker Desktop uruchamia się sam

## Rano – start (2 minuty)

```powershell
cd "C:\Users\kam05\Desktop\mdoel 1 hackathon\model_predykcyjny_hackathon_oczyszczalnie_sciekow"
.venv\Scripts\Activate.ps1
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $env:PYTHONIOENCODING = "utf-8"
docker compose up -d db
```

## Dostajemy dane finalne

1. Wrzuć pliki do `Dane\finalne\` (nie nadpisuj istniejących `Dane\CH|RU|RY`).
2. Dla każdego pliku z energią:
   ```powershell
   python main.py prognoza --plik "Dane\finalne\PLIK.csv" --obiekt RY_PZ1
   ```
   - program sam rozpozna format: licznik `data;godzina;typ;wartosc;status` (jak `mock_*`), raport dystrybutora
     (jak `Rap_godzinowy`) albo `czas;kwh`,
   - **jeśli wypisze „UWAGA: X% godzin z pliku model widział w treningu”** – dodaj `--uczciwie`
     (trening od nowa bez okresu pliku, ~2 min) – to jest wynik do pokazania,
   - `--obiekt`: nazwa z bazy (`RY_PZ1`, `RY_PNB1`, `CH_T`, `RU_W`, `RU_ZMP`) = dociągnięta historia;
     nowa pompownia: dowolna nazwa + `--stacja RY` (plik musi mieć ≥ 5 tygodni),
   - bez internetu: `--bez-pogody-biezacej` (prognoza na jutro bez bieżącej pogody).
3. Wyniki: `wyniki\prognoza\<obiekt>_prognoza.csv | _metryki.json | _prognoza.png`.
   W konsoli: WAPE dobowe modelu i porównanie z „wczoraj”, „tydzień temu”, „mediana 4 tygodni”.
4. Nieznany format pliku → w Excelu dwie kolumny `czas;kwh` (czas lokalny = początek godziny) i znowu punkt 2.
   Jeśli czas oznacza koniec godziny: `--koniec-godziny`.

### Anomalie na danych finalnych
- Aplikacja → wgraj CSV godzinowy (`czas, kwh` + opcjonalnie `obiekt_id, m3, opad_mm, temp_c`) →
  Detekcja → źródło „Aktywny zbiór – CSV godzinowy” → Uruchom.
- Pełne dane w formatach z `Dane\` → skopiuj do odpowiedniego folderu miasta, `python main.py etl`,
  `python main.py anomalie`.

## Pokaz w aplikacji (kolejność)

1. `python main.py aplikacja` → http://localhost:8501 (baza wczytuje się sama)
2. **Panel po lewej** → Wgraj pliki → **Wczytaj pliki** → sprawdź „Której pompowni dotyczą dane do prognozy?”
3. **Dane** → podgląd, statystyki (jak w Detektorze GUS) · **Wykresy** → przebieg, histogram, boxplot
4. **Prognoza** → **Przygotuj prognozę** → kafelki, opis prostym językiem, wykres jutra, „jak trafiały prognozy”, **Excel**
5. **Prognoza – szczegóły** → zużycie na tle deszczu i temperatury, jutro z prognozą pogody, porównanie z prostymi metodami
6. **Model** → jak dobry jest model ogólnie (vs proste reguły, per pompownia, doby suche/mokre)
7. **Raport** / **Pytanie** (LLM, jeśli dozwolony) · **Dobre praktyki** – jak przygotować plik
6. (opcjonalnie) anomalie: `$env:POKAZ_ANOMALIE = "1"` przed uruchomieniem aplikacji

## Liczby na slajdy (stan na 26.10)

| Co | Wynik |
|---|---|
| prognoza dobowa, test 30% (wszystkie obiekty) | **WAPE 13,9%** vs profil 4 tygodni 16,8%, wczoraj 20,1%, tydzień temu 23,9% |
| doby suche / mokre | 7,0% / 24,0% (z idealną pogodą: 5,5% / 19,5%) |
| **uczciwy test PZ1, rok X.2024–IX.2025** | **WAPE dobowe 8,6%** vs wczoraj 9,2%, mediana 4 tyg. 11,6%, tydzień temu 13,2%; sumy miesięczne ±4% (poza anomalią XI–XII 2024) |
| model bez Rybnika w treningu (PZ1) | 8,3% |
| anomalie – walidacja na alarmach CH | zespół trafia w doby z alarmem **2,4–2,6× częściej niż losowo** |
| powódź IX 2024 | wykryta na 4/4 obiektach jako dopływ opadowy |
| wody obce | CH 32%, RU_W 32%, PNB1 26% (wysoki przepływ nocny 0,73 → infiltracja), PZ1 9% |

## Gdy coś nie działa

| Objaw | Rozwiązanie |
|---|---|
| `UnicodeDecodeError` przy połączeniu z bazą | lokalny PostgreSQL zajmuje port – baza jest na **5435** (`etl\config.py`, `docker-compose.yml`) |
| w pomocy `main.py` nie ma `prognoza` | stara wersja – rozpakuj najnowszy zip (`Get-ChildItem ...sciekow*.zip`, najnowszy) |
| „Brak wytrenowanego modelu” | `python main.py prognoza --trenuj` |
| „Za mało danych” | plik + historia z bazy < 5 tygodni → podaj `--obiekt` z bazy albo dłuższy plik |
| Ollama niedostępna | raport powstaje jako same fakty; reszta działa |
| brak internetu | ETL bierze pogodę z `cache\`; prognoza: `--bez-pogody-biezacej` |

Jak przygotować prezentację (slajdy, zrzuty, demo, pytania jury): **`PREZENTACJA.md`**.

## Przed konkursem: nowe modele (prognoza na tydzień i plan na 2 miesiące)

```powershell
python main.py etl                              # nowa tabela: prognozy pogody wydane 1–7 dni wcześniej
python main.py strojenie                        # opcjonalnie, ~15–20 min
python main.py prognoza --trenuj --dni 7        # modele 1–7 dni + plan 2 miesiące, ~10–15 min
python main.py horyzont ; python main.py horyzont --dlugi   # liczby na slajd „błąd vs dni naprzód”
```
W aplikacji: **Prognoza → Na ile do przodu: Jutro / Tydzień / 2 miesiące**.

## Priorytety (odpowiedź organizatorów)
**1. Wody przypadkowe** (główny temat) → zakładki **Wody przypadkowe**, **Detekcja anomalii**, **Anomalie**
(`python main.py anomalie` przed pokazem – flagi ML na wykresach). **2. Energia w korelacji z opadem** → Wody przypadkowe
(kWh na 1 mm), Prognoza, Prognoza – szczegóły. Plan prezentacji: `PREZENTACJA.md`.

## Dane finalne RYBNIK (test!) – przepływ i energia PZ1, PNB1 2025–2026, BEZ opadu

Odpowiedzi organizatorów (1.3): w teście tylko **przepływ ścieków (m³) i zużycie energii** dwóch pompowni Rybnika; opad zdobywamy
sami – mamy Open-Meteo dla punktu Rybnik w `cache\` (pobrane do ~21.10.2026, działa bez internetu na miejscu).
1. Pliki do `Dane\RY\` obok dotychczasowych: przepływ `PZ1_*.txt` / `PNB1_*.txt` (format jak `PZ1_2024.txt`), energia – raport
   dystrybutora (CSV z nagłówkiem PPE / Płatnik; w nazwie musi być **PZ1** albo **PNB1**). Inny format? Plik energii można też wgrać
   wprost w aplikacji (panel → rozpozna licznik / raport / czas;kwh / Excel).
2. `python main.py etl` → `python main.py anomalie` → `python main.py zdarzenia` → `python main.py aplikacja` (jak niżej).
3. Okresy błędnych danych (np. III 2024 PZ1) – nie analizować (ETL odcina; nowe – dopisać w `etl/config.py` `ODETNIJ_PRZEPLYW_DO`).
4. Wynik: `wyniki\zdarzenia_wod_przypadkowych.xlsx` (dzień, godziny, objętość, koszt) + raporty z aplikacji.

## Dane finalne z Rudy (gdyby były: opad, energia godzinowa, SCADA co 20 s) – krok po kroku

1. Skopiuj pliki do `Dane\RU\` **obok** dotychczasowych (nie podmieniaj): energia `energia_*-W.csv` / `energia_*-ZMP.csv`
   (format `Data_godzina;Wartosc_kWh`), opad `intensywnosc_opadu*.csv`, SCADA `SCADA_w_*.csv` / `SCADA_ZMP_*.csv`.
   Inna nazwa? Zmień ją na pasującą do wzorca. Powtórzone godziny: wygrywa plik później w kolejności alfabetycznej.
2. ```powershell
   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $env:PYTHONIOENCODING = "utf-8"
   python main.py etl 2>&1 | Tee-Object log_etl_final.txt
   python main.py anomalie 2>&1 | Tee-Object log_anomalie_final.txt       # ML: IF + LOF + SVM, typy, walidacja
   python main.py zdarzenia 2>&1 | Tee-Object log_zdarzenia_final.txt     # WYNIK: dzień, godziny, objętość, koszt (1 zł/kWh)
   python main.py aplikacja
   ```
3. **Do oddania** (dysk w chmurze): `wyniki\zdarzenia_wod_przypadkowych.xlsx` (Zdarzenia / Podsumowanie / Metoda) + `.csv`,
   `wyniki\wody_przypadkowe_ranking.csv`, `wyniki\anomalie\`, repozytorium z kodem.
4. Prognoza energii z pliku Rudy: w aplikacji panel → wgraj `energia_*-W.csv` (format rozpoznawany sam) → pompownia RU_W.

## Kryteria oceny (organizatorzy) → co pokazujemy
| Kryterium | Pkt | U nas |
|---|---|---|
| Test ML / AI (9:00, 30 pytań, 15 min, wspólne konto) | 0–10 | – |
| Przygotowanie danych i algorytmy | 0–15 | ETL (zmiana czasu, liczniki, odrzucone błędne okresy, kontrola z fakturami), baza bezdeszczowa, IF+LOF+SVM, XGBoost + Optuna |
| Ocena modelu („model produkcyjny”) | 0–15 | walidacja na alarmach (lift 2,6×), powódź IX 2024, uczciwy test energii 13,0%, testy automatyczne, Docker |
| Wizualizacja i interfejs | 0–10 | aplikacja: Wody przypadkowe (wykresy zdarzeń z opadem), Anomalie, Prognoza, raport Excel z wykresami |

## Pokaz anomalii w aplikacji (temat główny)
1. **Wody przypadkowe** – ranking, pompownia RU_W (dopływ opadowy), RY_PNB1 (infiltracja), zdarzenie godzina po godzinie.
2. **Anomalie** → „Pompownia z bazy” → RU_W → **Wykryj anomalie** (~30 s) → kafelki, opis, oś czasu, tabela dzień / godziny / objętość
   → **Raport anomalii w Excelu**. Dla danych finalnych: wgraj plik w panelu → „Dane z panelu (okres z pliku)”.
3. **Anomalie – szczegóły** – głosowanie IF / LOF / SVM, przyczyny, walidacja na alarmach CH, znane zdarzenia.
