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
