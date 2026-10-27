# etl/ – dane z pompowni do bazy

ETL (Extract, Transform, Load) zamienia surowe pliki od organizatorów – liczniki, raporty dystrybutora, SCADA, opad,
faktury – w **jednolite, oczyszczone tabele godzinowe** w Postgresie. Z tych tabel korzystają modele, prognoza
i aplikacja. Pełny opis z diagramami: `docs/ETL_opis.docx`.

```powershell
python main.py etl 2>&1 | Tee-Object log_etl.txt      # ~1,5 min; każde uruchomienie ładuje wszystko od zera
```

## Pliki

| Plik | Za co odpowiada |
|---|---|
| `config.py` | **ustawienia:** połączenie z bazą (`DB_URL`, port 5435), ścieżka do `Dane`, lista pompowni z parametrami pomp, punkty pogody (CH/RU/RY), kalendarz szkolny woj. śląskiego, okresy do odcięcia, `PROGNOZA_OD` |
| `wspolne.py` | **trzy wspólne przekształcenia** (serce ETL): czas lokalny → UTC z rozpoznaniem jesiennej zmiany czasu, licznik narastający → przyrost godzinowy, energia „koniec godziny” → początek godziny UTC |
| `ch.py` | Chorzów: licznik energii, licznik ścieków, alarmy tłoczni |
| `ru.py` | Ruda Śląska: energia W i ZMP, opad z deszczomierza, SCADA (agregaty godzinowe) |
| `ry.py` | Rybnik: raporty godzinowe dystrybutora, liczniki przepływu, faktury (`wczytaj_raport` używa też tryb prognozy) |
| `zewnetrzne.py` | Open-Meteo: pogoda ERA5 i **prognoza wydana dzień wcześniej** (Previous Runs API), kalendarz (święta, mostki, ferie, wakacje); kontrole opadu |
| `baza.py` | tworzenie tabel, czyszczenie, zapis |
| `main.py` | kolejność kroków, log jakości, kontrole faktur i opadu |

Zmiennymi środowiskowymi można nadpisać: `DB_URL`, `DANE_DIR`, `CACHE_DIR`.

## Szczegóły



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

## Nowe dane (np. na konkursie)

- **Plik z zużyciem energii do prognozy** nie wymaga ETL – wgrywa się go w aplikacji (albo `python main.py prognoza --plik`).
- **Pełne dane w formatach z `Dane\`** (np. nowy rok SCADA): skopiuj do folderu miasta i uruchom `python main.py etl`,
  potem `python main.py prognoza --trenuj`, żeby model uczył się także na nich.
- **Nowe źródło / pompownia**: wpis w `OBIEKTY` w `config.py` + funkcja wczytująca w pliku miasta + krok w `main.py`.
