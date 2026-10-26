# Model predykcyjny – hackathon oczyszczalnie ścieków

Smart Water Challenge 2026. Jeden program, dwa etapy:

1. **ETL** – surowe pliki z `Dane/` + pogoda + kalendarz → oczyszczone tabele godzinowe w Postgresie,
2. **Model** – prognoza zużycia energii na następną dobę: kilka wariantów modeli porównanych na zbiorze testowym.

```
Dane/  ──►  ETL  ──►  Postgres (smartwater)  ──►  modele  ──►  wyniki/
```

## Struktura

```
hacathon scieki/
├── Dane/                                   surowe pliki (CH, RU, RY) – tylko do odczytu
└── model_predykcyjny_hackathon_oczyszczalnie_sciekow/
    ├── main.py                 punkt wejścia: etl | model | wszystko
    ├── docker-compose.yml      baza (postgres:16) + aplikacja
    ├── Dockerfile, requirements.txt
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
    │   └── eksperymenty.py     lista wariantów i porównanie
    ├── sprawdz_baze.ipynb      podgląd bazy po ETL
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
docker compose run --rm app model --warianty xgb_opad_przeszly,naiwny_tydzien
```

- Baza startuje sama i zostaje włączona: `localhost:5432`, baza `smartwater`, `hack` / `hack`.
- Wyniki modeli lądują w `wyniki/` na dysku, pogoda w `cache/`.
- **Pierwszy ETL potrzebuje internetu** (pogoda); kolejne działają z `cache/` także offline.

## Uruchomienie – lokalnie (venv)

```powershell
python -m pip install -r requirements.txt
docker compose up -d db                     # sama baza
python main.py wszystko                     # albo: etl / model
```
Na macOS, jeśli XGBoost zgłosi brak `libomp`: `brew install libomp`.

## Najczęstsze problemy

| Objaw | Rozwiązanie |
|---|---|
| port 5432 zajęty / działa stary kontener `smartwater-db` | `docker rm -f smartwater-db` albo w `docker-compose.yml` zmień na `"5433:5432"` |
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
  (nie liczy szczytów), dlatego warianty `_kal` mają **kalibrację**: mnożnik per obiekt = suma rzeczywista / suma prognozy
  na zbiorze walidacyjnym.
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
| `xgb_prognoza_pogody_kal` | jw. + kalibracja sum per obiekt |
| `xgb_pogoda_rzeczywista` | pogoda w godzinie prognozy = „idealna prognoza pogody” (górna granica) |
| `xgb_per_obiekt` | osobny model dla każdego obiektu |
| `xgb_transfer_RY` | uczony tylko na CH i RU, testowany na Rybniku |
| `xgb_transfer_RY_prognoza` | jw. + prognoza pogody |

Nowe warianty: słownik `WARIANTY` w `model/eksperymenty.py`; grupy cech w `model/cechy.py`.

## Wyniki (`wyniki/`)

- `metryki.csv` – MAE, RMSE [kWh/h], WAPE godzinowe i dobowe [%], WAPE dobowe osobno dla dób suchych i mokrych
  (opad > 1 mm), bias [%], poprawa vs naiwny tydzień
- `prognozy_test.csv.gz` – prognozy wszystkich wariantów na zbiorze testowym
- `test_<obiekt>.png` – rzeczywistość vs 3 najlepsze warianty
- `waznosc_<wariant>.png/.csv` – ważność cech

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
