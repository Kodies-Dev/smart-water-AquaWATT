# Jak przygotować prezentację

Plan na **~6 minut slajdów + ~3 minuty demo + pytania**. Jeśli organizatorzy podadzą inny czas – skracaj slajdy 3 i 8,
nigdy demo i wyników. Wszystkie liczby poniżej pochodzą z uruchomień na prawdziwych danych (stan 26.10.2026) – przed
konkursem odśwież je z `log_model.txt` i zakładki **Model**.

---

## 0. Priorytety (odpowiedź organizatorów)

**Temat główny: wykrywanie wód przypadkowych** (infiltracja, nielegalne podłączenia). **Temat drugi: prognoza zużycia
energii, przede wszystkim w korelacji z opadami.** Prezentacja idzie w tej kolejności – energia jest „ceną” wód przypadkowych.

## 1. Historia w jednym zdaniu

> **„W kanalizacji rozdzielczej co trzeci m³ w części pompowni to nie ścieki z domów, tylko wody przypadkowe – deszcz
> z nielegalnych podłączeń i wody gruntowe przez nieszczelności. Pokazujemy, gdzie ich jest najwięcej i jakiego typu,
> ile energii kosztują, i prognozujemy zużycie energii z uwzględnieniem deszczu.”**

Układ: **problem → dane → wody przypadkowe (metoda + wyniki + ML) → energia vs deszcz → prognoza → produkt (demo) → wartość.**

---

## 2. Slajdy

### Slajd 1 – Tytuł
- „Wody przypadkowe i energia pompowni ścieków – wykrywanie i prognoza”.
- Jedna liczba: **„do ~1/3 objętości ścieków to wody przypadkowe (CH_T, RU_W)”** (sprawdź w zakładce Wody przypadkowe).

### Slajd 2 – Problem
- Kanalizacja rozdzielcza: do pompowni powinny płynąć **tylko ścieki bytowe**.
- **Infiltracja** – wody gruntowe przez nieszczelne rury i studnie: stały dopływ, widoczny **w nocy**.
- **Dopływ opadowy** – rynny, odwodnienia, kanalizacja deszczowa **nielegalnie podłączone**: skok przepływu **w dniu deszczu**.
- Skutek: przeciążenie pomp i oczyszczalni, **większe zużycie energii**, ryzyko wybić przy ulewach.

### Slajd 3 – Dane i ich przygotowanie
- 3 miasta, 5 pompowni, ~88 tys. godzin: liczniki energii i ścieków, SCADA, deszczomierz, faktury, alarmy tłoczni.
- ETL do Postgresa: zmiana czasu, liczniki → przyrosty, odrzucone 0,4–1% wierszy, faktury zgodne w 30/33 miesiącach (±1%).
- Pogoda Open-Meteo: pomiary (zgodność z deszczomierzem 0,79) i **prognozy wydane 1–7 dni wcześniej**.

### Slajd 4 – Metoda: jak mierzymy wody przypadkowe (reguły, przejrzyste)
- **Baza bezdeszczowa** – typowy przepływ / energia w suche dni (ten sam dzień tygodnia, ostatnie tygodnie).
- **Nadwyżka = rzeczywiste − baza** → udział wód przypadkowych w objętości i w energii.
- **Infiltracja** – przepływ nocny (02–05) / średni w suche dni (ścieki bytowe: ok. 0,3–0,45; > 0,6 = wysoka).
- **Dopływ opadowy** – nadwyżka na 1 mm deszczu (regresja na dniach z opadem) i korelacja opad ↔ nadwyżka.
- Grafika: zakładka **Wody przypadkowe** → wykres pompowni (czerwone pole = wody przypadkowe nad bazą, deszcz u góry).

### Slajd 5 – Wyniki: gdzie i jakie wody przypadkowe (liczby z zakładki Wody przypadkowe)
| Pompownia | Wody przypadkowe | Przepływ nocny (infiltracja) | Reakcja na deszcz | Energia na wody |
|---|---|---|---|---|
| CH_T | ~32% objętości | 0,42 – niska | silna | ~30% |
| RU_W | ~32% | 0,49 – umiarkowana | silna | ~35% |
| RY_PNB1 | ~26% | **0,73 – wysoka → infiltracja** | umiarkowana | ~28% |
| RY_PZ1 | ~9% | 0,37 – niska | gwałtowna przy ulewach | ~8% |
| RU_ZMP | (bez przepływomierza) | – | słaba (po energii) | ~9% |
- **Wniosek dla eksploatacji:** CH_T i RU_W – szukać podłączeń deszczowych (inspekcja, testy dymowe);
  PNB1 – szukać nieszczelności (inspekcja TV kanałów, pomiary nocne).
- Grafika: wykres rankingu (udział w objętości i w energii) + tabela.

### Slajd 5b – Wynik w formacie organizatorów: zdarzenia (dzień, godziny, objętość)
- Godzinowa baza bezdeszczowa → **zdarzenie = kolejne godziny z nadwyżką** (≥ 25% bazy i > 3 odchylenia typowe).
- Dla każdego zdarzenia: **dzień, godziny od–do, objętość m³ ponad bazę**, opad w trakcie i 6 h przed, nadwyżka energii,
  **koszt przy 1 zł/kWh**, typ (opadowe / bez opadu → infiltracja, zrzut, awaria).
- Liczby z `python main.py zdarzenia` (podsumowanie per pompownia) + wykres jednego zdarzenia godzina po godzinie
  (zakładka Wody przypadkowe → „Pokaż zdarzenie na wykresie godzinowym”).
- Plik do oddania: `wyniki\zdarzenia_wod_przypadkowych.xlsx`.

### Slajd 6 – ML: wykrywanie nietypowych dni (zakładki Detekcja / Anomalie)
- Zespół **Isolation Forest + LOF + One-Class SVM** (≥ 2 z 3), osobno dla każdej pompowni, + tryb panelowy
  (nagła zmiana, odstawanie od innych pompowni tego samego dnia).
- Typ każdej anomalii: dopływ opadowy, infiltracja / dopływ bez deszczu, roztopy, spadek sprawności pomp,
  zmiana nastaw, spiętrzenie…
- **Walidacja na alarmach tłoczni CH: wskazania 2,6× częściej przy alarmach niż losowo**; **powódź IX 2024 wykryta na
  4/4 pompowniach jako dopływ opadowy**; odsetek dobrany automatycznie (5%, ~145 dni).

### Slajd 7 – Energia a deszcz (temat drugi)
- Zakładka **Wody przypadkowe** → wykres „Energia: nadwyżka vs opad”: **kWh na 1 mm deszczu** i korelacja dla każdej pompowni.
- Prognoza energii na jutro **z prognozą deszczu**: **13,0%** średniego błędu dobowego (Optuna, test otwierany raz;
  bez strojenia 13,75%); proste metody 16,8–20,1%. Doby suche ~7%, z deszczem ~24% – **błąd siedzi w ulewach**.
- **Trafność prognozy deszczu vs wyprzedzenie** (korelacja z deszczomierzem): 0,68 / 0,67 / 0,67 / **0,53** / 0,40 / 0,39 / **0,31**
  dla 1…7 dni → błąd prognozy energii: 13,1% → 16,5%; od 6. dnia jak „typowy dzień” (16,8%).
- Grafika: `wyniki\horyzont.png` + zakładka **Prognoza – szczegóły** (zużycie na tle deszczu zmierzonego i prognozowanego).

### Slajd 8 – Produkt (demo)
- Aplikacja w przeglądarce: **Wody przypadkowe** (ranking, wykresy, dni do sprawdzenia) → **Detekcja / Anomalie** (ML) →
  **Prognoza** (jutro / tydzień / plan 2 miesiące) → **Raport w Excelu z wykresami**.
- Dane od klienta: plik CSV/Excel z licznika (rozpoznawany sam); reszta (pogoda, kalendarz) automatycznie.

### Slajd 9 – Wartość i dalsze kroki
- **Gdzie szukać**: lista pompowni i dni do inspekcji (infiltracja vs podłączenia), **ile to kosztuje** (kWh/rok).
- **Planowanie energii**: prognoza z deszczem na 1–3 dni dokładna, tydzień orientacyjnie, 2 miesiące – budżet z przedziałem.
- Dalej: przepływomierze na wszystkich pompowniach, inspekcje w zlewniach z najwyższą reakcją na deszcz, alerty na żywo.

---

## 2b. Kryteria oceny → slajdy
Przygotowanie danych i algorytmy (15 pkt): slajdy 3, 4, 6 · Ocena modelu / „model produkcyjny” (15): slajdy 5b, 6, 7 + testy,
Docker, uczciwe sprawdzenie · Wizualizacja i interfejs (10): slajd 8 + demo. Jury chce też **opisu metody i przygotowania danych**
(nie tylko wyniku) – slajd 4 i `README.md` / `etl/README.md` / `model/README.md`.

## 3. Zrzuty ekranu do zrobienia (przed konkursem)

Uruchom `python main.py aplikacja`, ustaw okno przeglądarki ~1600 px szerokości, zrób zrzuty (Win+Shift+S):

| Zrzut | Gdzie | Ustawienia |
|---|---|---|
| ranking + tabela wód przypadkowych | **Wody przypadkowe** | – |
| wykres pompowni (czerwone pole) + korelacja z deszczem | **Wody przypadkowe** | pompownia RU_W albo CH_T, potem RY_PNB1 (noc) |
| oś czasu anomalii + typy | **Detekcja anomalii** → **Anomalie** | Uruchom detekcję (z bazy) |
| kafelki + wykres wariantów | **Model** | – |
| doby suche vs mokre, ważność cech | **Model** | przewiń w dół |
| kafelki + opis + wykres jutra | **Prognoza** | plik `01_PZ1_8tyg_licznik_mock.csv`, RY_PZ1, Przygotuj |
| „Jak trafiały prognozy” | **Prognoza** | jw. |
| zużycie na tle deszczu | **Prognoza – szczegóły** | plik `09_CH_T_10tyg_licznik_mock.csv`, widok dobowo |
| panel z rozpoznanym plikiem | panel boczny | po „Wczytaj pliki” |

Wykresy Plotly mają w prawym górnym rogu ikonę aparatu – zapisuje PNG w wysokiej jakości.

---

## 4. Demo na żywo (~3–4 min)

0. *(60 s, najpierw – temat główny)* **Wody przypadkowe** → ranking → pompownia RU_W: „czerwone pole to wody przypadkowe,
   tu deszcz, tu nadwyżka”; RY_PNB1: „wysoki przepływ nocny = infiltracja”. **Anomalie**: oś czasu z typami.

Przygotowanie: aplikacja uruchomiona, baza działa, model wytrenowany, plik pod ręką, **karta przeglądarki odświeżona**.

1. *(20 s)* „To jest plik z odczytami licznika – taki jak dostaliśmy od organizatorów.” → panel → **Wgraj pliki** →
   **Wczytaj pliki** → „program sam rozpoznał format i pompownię”.
2. *(20 s)* **Dane** → podgląd i statystyki („tu można obejrzeć i obrobić dane – narzędzia z naszego wcześniejszego projektu”).
3. *(60 s)* **Prognoza** → **Przygotuj prognozę** → podczas liczenia: „model uczy się od nowa bez tego okresu,
   żeby sprawdzenie było uczciwe”. Wynik: przeczytaj 2 kafelki (prognoza na jutro, średni błąd) i pierwsze zdanie opisu.
   Pokaż wykres „jak trafiały prognozy” – „zielone = błąd poniżej 10%”.
4. *(40 s)* **Prognoza – szczegóły** → „tu widać, dlaczego się mylimy: deszcz, którego prognoza nie przewidziała”.
5. *(20 s)* **Raport w Excelu (z wykresami)** – otwórz plik: podsumowanie, wykresy, tydzień i plan.
6. *(opcjonalnie)* **Raport** → „Generuj raport” (tylko jeśli LLM dozwolony i Ollama działa – inaczej pomiń).

**Plan B:** jeśli coś nie działa na żywo – pokaż zrzuty z punktu 3. Jeśli nie ma internetu – w ustawieniach
zaawansowanych odznacz „Pobierz aktualną prognozę pogody”. Uczciwe sprawdzenie trwa 1–2 min: jeśli jest mało czasu,
odznacz je (wtedy aplikacja pokaże ostrzeżenie, że model widział te dane – powiedz to wprost).

---

## 5. Pytania jury – przygotowane odpowiedzi

| Pytanie | Odpowiedź |
|---|---|
| **Skąd wiecie, że model nie „oszukuje”?** | Test na danych, których model nie widział (ostatnie 30% czasu, a w aplikacji – trening od nowa bez okresu z pliku); każda cecha korzysta tylko z danych sprzed ≥ 24 h; test automatyczny: zmiana przyszłości nie zmienia ani jednej cechy. |
| **Dlaczego XGBoost, a nie sieć neuronowa / LSTM?** | Dane tabelaryczne z kilkudziesięcioma cechami, ~88 tys. godzin – gradient boosting jest tu standardem, szybki (trening 1–2 min), interpretowalny (ważność cech); proste reguły jako punkt odniesienia pokazują realny zysk. |
| **Co, jeśli nowa pompownia?** | Model uczony bez Rybnika dał na Rybniku 8,3% – działa na nowych obiektach; wystarczy ~5 tygodni historii zużycia. |
| **Dlaczego w deszczowe dni błąd jest duży?** | Szczyty robią wody opadowe; prognoza deszczu sprzed doby ma ograniczoną trafność (zgodność 0,68, zawyża o 25%). Z idealną pogodą błąd spadłby z 13,9% do 11,2% – granica jest po stronie prognozy pogody. |
| **Model zaniża sumy (bias ok. −6%)?** | Celuje w medianę (najlepsza dla błędu dobowego), więc nie łapie pełnej skali ulew. Na spokojnych pompowniach bias −1…−3%. Do budżetu miesięcznego warto doliczyć zapas na dni deszczowe – aplikacja to mówi. |
| **Jakich danych potrzebuje klient?** | Tylko zużycia energii (plik z licznika). Przepływ i SCADA sprawdziliśmy – dają niewielki zysk, więc model główny ich nie wymaga. |
| **Czy model językowy wymyśla liczby?** | Nie liczy nic: opis dla klienta jest generowany w Pythonie; LLM (lokalny, offline) dostaje gotowe fakty z zakazem zmiany liczb, a fakty są zawsze dołączone do raportu. |
| **Czy stroiliście hiperparametry?** | Tak – Optuna z walidacją kroczącą tylko na części treningowej (3 okresy), test otwierany raz na końcu; dostrojone parametry trafiają do modelu tylko przy zysku ≥ 0,1 pp na teście. Liczbę drzew dobiera early stopping. (Podaj wynik z `python main.py strojenie`.) |
| **Czemu tydzień, a nie miesiąc szczegółowo?** | Prognoza deszczu traci trafność po 2–3 dniach, a archiwum prognoz pogody sięga 7 dni – dalej uczciwie sprawdzić się nie da. Na 2 miesiące dajemy plan dobowy z przedziałem, bez udawania dokładności godzinowej. |
| **Jak często trenować?** | Po każdej większej paczce danych (np. raz w miesiącu) – jedna komenda / przycisk, 1–2 minuty. |
| **Czemu na PNB1 „jak wczoraj” wygrywa?** | Bardzo równe zużycie i krótka historia (8 miesięcy) zaraz po powodzi – prosta reguła jest tam mocna; mówimy o tym otwarcie. |
| **Zmiana czasu, braki, resety liczników?** | Obsłużone w ETL i w aplikacji (testy automatyczne: jesienna powtórzona godzina, reset licznika, dziury w danych). |
| **Jak to wdrożyć?** | Docker (baza + aplikacja), działa lokalnie i offline (pogoda z pamięci podręcznej); dane nie opuszczają komputera. |

---

## 6. Wskazówki

- **Liczby zaokrąglaj** na slajdach (13,9% → „ok. 14%”), dokładne podawaj w odpowiedziach.
- **Jeden wykres na slajd**, opis wykresu w tytule (np. „W suche dni mylimy się o 7%, w deszczowe o 24%”).
- Mów **o kliencie** („dyspozytor wie, ile energii kupić na jutro”), nie o hiperparametrach.
- Ograniczenia (slajd 6) pokazuj sam – jury to docenia bardziej niż same dobre liczby.
- Przećwicz demo **2 razy na tym laptopie**, z tym plikiem, w tej sieci.

---

## 7. Checklista dzień przed

- [ ] liczby na slajdach zgodne z ostatnim `python main.py model` i zakładką Model
- [ ] zrzuty ekranu w folderze, wstawione do slajdów
- [ ] demo przećwiczone (czas < 3 min), plik demo w łatwo dostępnym miejscu
- [ ] plan B: zrzuty, wersja offline
- [ ] zgoda organizatorów na LLM – jeśli brak, nie pokazujemy zakładek Raport / Pytanie
- [ ] `DZIEN_KONKURSU.md` przejrzany (komendy na dane finalne)
