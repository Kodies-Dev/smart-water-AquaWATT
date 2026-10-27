# sql/ – schemat bazy

`schema.sql` wykonuje się przy każdym `python main.py etl` (`CREATE TABLE IF NOT EXISTS`, widok jest odtwarzany).
Baza: Postgres 16 w Dockerze, `127.0.0.1:5435`, baza `smartwater`, użytkownik / hasło `hack` / `hack`.

**Zasada czasu:** w każdej tabeli `czas` = **początek godziny w UTC** (`TIMESTAMPTZ`); kalendarz ma daty lokalne.

| Tabela | Klucz | Zawartość |
|---|---|---|
| `obiekty` | `obiekt_id` | 5 pompowni (CH_T, RU_W, RU_ZMP, RY_PNB1, RY_PZ1): miasto, pompy, moc, wydajność, zbiornik, punkt pogody |
| `energia_godz` | obiekt, czas | **zużycie energii kWh na godzinę – cel prognozy** |
| `energia_mies` | obiekt, miesiąc | faktury Rybnika (2023–2026) |
| `przeplyw_godz` | obiekt, czas | przepływ ścieków m³ na godzinę |
| `scada_godz` | obiekt, czas | Ruda: poziom w zbiorniku, prądy pomp, praca pomp, progi start/stop |
| `opad_godz` | stacja, czas | deszczomierz w Rudzie, mm/h |
| `pogoda_godz` | stacja, czas | Open-Meteo ERA5 dla CH/RU/RY: temperatura, opad, deszcz, śnieg, pokrywa, wilgotność gleby, parowanie |
| `prognoza_pogody_godz` | stacja, czas | prognoza pogody wydana ~24 h wcześniej: opad, deszcz, śnieg, temperatura |
| `kalendarz` | data | weekend, święto (z nazwą), dzień wolny, mostek, ferie, wakacje, przerwa świąteczna |
| `alarmy` | – | alarmy tłoczni Chorzów (sygnał, stan 0/1) |
| `etl_log` | – | log jakości każdego kroku ETL (wiersze przed / po) |
| `anomalie_dni` | – | wynik `python main.py anomalie` (tworzona przez pandas) |
| **`v_model`** (widok) | – | energia + przepływ + SCADA + opad + pogoda + prognoza + kalendarz w jednej godzinie, plus `czas_lokalny` |

Przykład:
```sql
SELECT obiekt_id, date_trunc('day', czas AT TIME ZONE 'Europe/Warsaw') AS dzien, SUM(kwh) AS kwh
FROM energia_godz GROUP BY 1, 2 ORDER BY 1, 2;
```
Podgląd bazy: notebook `sprawdz_baze.ipynb`.
