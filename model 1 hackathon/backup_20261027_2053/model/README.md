# model/ – prognoza zużycia energii

Dwie rzeczy:
1. **eksperymenty** (`python main.py model`) – kilkanaście wariantów modeli porównanych uczciwie na zbiorze testowym,
2. **model do pracy** (`python main.py prognoza`) – najlepszy wariant trenowany na wszystkich danych, zapisany do
   `modele\` i używany przez aplikację do prognozy z nowego pliku.

## Pliki

| Plik | Za co odpowiada |
|---|---|
| `config.py` | horyzont `H = 24 h`, podział 70/30, walidacja, parametry XGBoost (strata absolutna), `DB_URL` z `etl/config.py` |
| `dane.py` | wczytanie tabel z bazy |
| `cechy.py` | **`zbuduj()` – cechy, te same w treningu, ocenie i prognozie**; `podziel()` – podział chronologiczny |
| `modele.py` | baseline'y, regresja liniowa, XGBoost (globalny, per obiekt, transfer), kalibracja |
| `ocena.py` | metryki (MAE, RMSE, WAPE godzinowe i dobowe, bias, doby suche / mokre), wykresy |
| `eksperymenty.py` | lista wariantów, wybór per obiekt, tabele wyników → `wyniki\` |
| `prognoza.py` | **model do pracy**: trening na wszystkich danych (modele na 1..7 dni), zapis, wczytanie pliku (3 formaty), backtest, prognoza 24 h i 7 dni, uczciwy backtest |
| `strojenie.py` | **Optuna** z walidacją kroczącą w części treningowej; test otwierany raz; `modele/parametry_optuna.json` |
| `horyzont.py` | ocena prognozy na 1..7 dni naprzód (test) → `wyniki/horyzont.csv`, `horyzont.png` |
| `dlugi.py` | **plan na 2 miesiące**: model dzienny P10 / P50 / P90, klimatologia, kalibracja przedziału, ocena na wielu datach startu |

## Jak model „myśli”

Model przewiduje zużycie w każdej godzinie jutra **wyłącznie z tego, co jest znane dobę wcześniej**:

| Grupa cech | Ważność | Przykłady |
|---|---|---|
| historia zużycia | 53% | kWh 24/48/168/336 h wcześniej, średnie z doby i tygodnia, maksimum z doby, profil z 4 tygodni, zmiana poziomu |
| kalendarz | 17% | godzina, dzień tygodnia, miesiąc, pora roku, święto, dzień wolny, mostek, ferie, wakacje |
| prognoza pogody (wydana dzień wcześniej) | 11% | prognozowany opad 1/3/6/24 h, temperatura, śnieg |
| pompownia | 9% | która to pompownia (nowa = model ogólny) |
| pogoda z ostatnich dni | 7% | temperatura, pokrywa śnieżna i roztopy, wilgotność gleby, parowanie |
| opad z ostatnich dni | 3% | suma opadu z 24 h, 3 i 7 dni, miesiąca |

**Cel modelu:** `log(1 + kWh / poziom)`, gdzie poziom = mediana zużycia pompowni z 28 dni – jeden model dla
pompowni od ~35 do ~280 kWh/dobę. **Strata absolutna** – model celuje w medianę (zgodnie z WAPE).
Przepływu i SCADA model główny **nie używa** – wystarczy mu plik z energią.

## Eksperymenty – szczegóły

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

## Model do pracy – `prognoza.py`

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

## Przepływ prognozy (co dzieje się po kliknięciu „Przygotuj prognozę”)

1. **Uczciwość:** jeśli plik obejmuje okres z treningu, model uczy się od nowa w pamięci **bez** godzin pompowni od
   początku pliku (zapisany model zostaje).
2. **Seria wejściowa:** historia pompowni z bazy (sprzed pliku) + godziny z pliku + 24 puste godziny po ostatniej.
3. **Pogoda:** z bazy; ostatnie dni i jutro z bieżącej prognozy Open-Meteo.
4. **Cechy:** `zbuduj()` – identycznie jak w treningu.
5. **Model** liczy każdą godzinę → kWh.
6. **Backtest:** godziny z pliku vs prawda (każda prognoza tylko z danych sprzed ≥ 24 h) + porównanie z prostymi metodami.
7. **Prognoza:** 24 puste godziny z kroku 2.

Dane wejściowe ostatniej prognozy są dostępne jako `uruchom.ostatnie` (używa ich zakładka „Prognoza – szczegóły”).


## Strojenie hiperparametrów (`python main.py strojenie`)

- **Tylko część treningowa** (pierwsze 70% czasu każdej pompowni), **walidacja krocząca** (*rolling-origin CV*):
  3 okresy – uczenie do 55 / 70 / 85% części treningowej, ocena na kolejnych 15%; wynik = średni WAPE dobowy.
- Optuna (TPE, 30 prób / 20 min): `learning_rate`, `max_depth`, `min_child_weight`, `subsample`, `colsample_bytree`,
  `reg_lambda`, `reg_alpha`; liczbę drzew dobiera early stopping. Pierwsza próba = parametry domyślne.
- **Test otwierany raz**, na końcu: domyślne vs dostrojone. Model do pracy używa dostrojonych tylko przy zysku ≥ 0,1 pp
  (pole `uzyj` w `modele/parametry_optuna.json`) – mniejsza różnica to szum.

## Prognoza na kilka dni (1–7)

- **Osobny model na każdy dzień naprzód** (*direct multi-horizon*): dla K dni cechy historii przesunięte o ≥ 24·K h
  (`zbuduj(d, h=24*K)`; test automatyczny sprawdza brak podglądania przyszłości dla K = 1, 3, 7),
  **prognoza pogody wydana K dni wcześniej** (tabela `prognoza_pogody_dni`, Open-Meteo `previous_dayK`).
- Prognoza: godziny dnia +K liczone modelem K; przyszła pogoda – bieżąca prognoza Open-Meteo (do 16 dni).
- Ocena: `python main.py horyzont` – WAPE dobowe na teście dla K = 1..7 vs „tak jak K dni temu” i typowy dzień.
- Granica 7 dni: archiwum prognoz pogody sięga 7 dni wstecz – dalej nie da się uczciwie sprawdzić wpływu prognozy pogody.

## Plan na 2 miesiące (`dlugi.py`)

- Pogody na tygodnie naprzód nikt nie zna → model **dzienny** na kalendarzu, porze roku, poziomie pompowni z ostatnich
  28 dni, zmianie poziomu, tym samym okresie rok wcześniej i **klimatologii** (typowy opad, szansa deszczu, temperatura
  dla dnia roku, 2023–2026).
- Uczenie na **datach startu co 3 dni**: dla startu o i dnia t = o+1..o+60 tylko cechy znane w dniu o.
- **Regresja kwantylowa** (P10, P50, P90) + **kalibracja szerokości przedziału** na odłożonych 20% startów, żeby przedział
  obejmował ~80% dni (bez kalibracji tylko ~55%).
- Ocena (`python main.py horyzont --dlugi`): starty z ostatnich 30% czasu każdej pompowni, model uczony na dniach
  przed nimi; WAPE dobowe dla 1–7, 8–14, 15–30, 31–60 dni vs „średnia z ostatnich 4 tygodni” i „rok temu”, pokrycie
  przedziału, błąd sumy 30-dniowej.
