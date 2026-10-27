# Jak przygotować prezentację

Plan na **~6 minut slajdów + ~3 minuty demo + pytania**. Jeśli organizatorzy podadzą inny czas – skracaj slajdy 3 i 8,
nigdy demo i wyników. Wszystkie liczby poniżej pochodzą z uruchomień na prawdziwych danych (stan 26.10.2026) – przed
konkursem odśwież je z `log_model.txt` i zakładki **Model**.

---

## 1. Historia w jednym zdaniu

> **„Pompownia zużywa tyle energii, ile ścieków musi przepompować – a ilość ścieków zależy od kalendarza i deszczu.
> Nasz model przewiduje zużycie na jutro z błędem ok. 9% na typowej pompowni i pokazuje to klientowi w 2 minuty:
> wgrywa plik, dostaje prognozę i Excel.”**

Układ: **problem → dane → podejście → wyniki → gdzie się myli → produkt (demo) → wartość i dalsze kroki.**

---

## 2. Slajdy

### Slajd 1 – Tytuł
- Nazwa zespołu, „Prognoza zużycia energii pompowni ścieków na następną dobę”.
- Jedna liczba dużą czcionką: **„~9% średniego błędu dobowego (Rybnik, cały rok, uczciwy test)”**.

### Slajd 2 – Problem
- Pompownie zużywają energię proporcjonalnie do ilości ścieków (kWh/m³ stałe: CH ≈ 0,17, RU ≈ 0,29).
- Ilość ścieków = rytm dnia i tygodnia (domy) **+ wody opadowe** (deszcz, roztopy) – to one robią szczyty 2–5× normy.
- Cel: **prognoza na dobę naprzód** – do zakupu energii, planowania pracy pomp, wychwytywania nietypowych dni.
- Grafika: zakładka **Prognoza – szczegóły**, widok dobowo – zużycie na tle deszczu (szczyty pod słupkami deszczu).

### Slajd 3 – Dane i ich przygotowanie
- **3 miasta, 5 pompowni, ~88 tys. godzin** (2024–2026): liczniki, raporty dystrybutora, SCADA, opad, faktury.
- Przygotowanie (ETL do Postgresa): zmiana czasu (powtórzona godzina jesienią), liczniki → przyrosty godzinowe,
  odrzucone tylko 0,4–1% wierszy; **kontrola z fakturami: 30 z 33 miesięcy zgodne co do 1%**.
- Pogoda Open-Meteo: pomiary (zgodność z deszczomierzem 0,79) i **prognoza wydana dzień wcześniej** (0,68) + kalendarz
  (święta, mostki, ferie śląskie).
- Grafika: prosty schemat `pliki → ETL → baza → model → aplikacja` (z README).

### Slajd 4 – Podejście (model)
- **XGBoost**, jeden model dla wszystkich pompowni (przewiduje zużycie względem typowego poziomu pompowni).
- **Tylko to, co wiadomo dobę wcześniej** – historia, kalendarz, pogoda do chwili prognozy, **prognoza pogody**.
- Ważność cech: **historia zużycia 53% · kalendarz 17% · prognoza pogody 11% · pompownia 9% · pogoda 7% · opad 3%**.
- **Uczciwość:** test na ostatnich 30% czasu każdej pompowni, których model nie widział; test automatyczny
  sprawdza, że cechy nie „podglądają przyszłości”.
- Grafika: zakładka **Model → „Z czego korzysta model główny”**.

### Slajd 5 – Wyniki
| Metoda | Średni błąd dobowy (wszystkie pompownie) |
|---|---|
| **nasz model** | **13,9%** |
| mediana z 4 tygodni | 16,8% |
| „jak wczoraj” | 20,1% (model o 31% lepszy) |
| „jak tydzień temu” | 23,9% |
- **Rybnik PZ1, cały rok X.2024–IX.2025, model uczony bez tego roku: 8,6%**; sumy miesięczne ±4%
  (poza okresem nietypowego spadku zużycia XI–XII 2024).
- **Model uczony bez Rybnika, test na Rybniku: 8,3%** – przenosi się na nowe pompownie.
- Grafika: zakładka **Model** – kafelki + wykres wszystkich wariantów (czerwony = nasz, szare = proste metody).

### Slajd 6 – Gdzie się myli i dlaczego (to buduje zaufanie)
- **Doby suche: 7,0% · doby z deszczem: 24,0%.**
- Gdyby prognoza pogody była idealna: 11,2% (mokre 19,5%) → **ograniczeniem jest prognoza deszczu, nie model**
  (prognoza sprzed doby zawyża opad o ok. 25%).
- Spokojne pompownie (RU_ZMP 5,8%, PZ1 8,6%) vs „deszczowe” (CH 25%, RU_W 22%).
- Uczciwie: na RY_PNB1 prosta metoda „jak wczoraj” bywa lepsza (bardzo równe zużycie, krótka historia).
- Grafika: zakładka **Model → „doby suche vs mokre”** albo **Prognoza – szczegóły** dla Chorzowa (plik `09`).

### Slajd 6b – Jak daleko naprzód (nowe)
- **Jutro**: godzinowo, z prognozą pogody – najdokładniej.
- **Tydzień**: osobny model na każdy dzień, z prognozą pogody wydaną tyle dni wcześniej; błąd rośnie z horyzontem
  (liczby z `python main.py horyzont` – wykres `wyniki\horyzont.png`).
- **2 miesiące**: plan dobowy z przedziałem P10–P90 (skalibrowany: ~80% dni w przedziale), bez prognozy pogody –
  do budżetu i zakupu energii (liczby z `python main.py horyzont --dlugi`).
- Grafika: `wyniki\horyzont.png` + zrzut planu z zakładki Prognoza (2 miesiące).

### Slajd 7 – Produkt (zapowiedź demo)
- Aplikacja w przeglądarce dla osoby, która **nie zna się na modelach**: plik → „Przygotuj prognozę” →
  prognoza na 24 h, średni błąd w % i kWh, opis prostym językiem, **Excel**.
- Formaty: odczyty licznika (jak dane od organizatorów), raport dystrybutora, `czas;kwh` – rozpoznawane same.
- Opis wyników liczony w Pythonie (zawsze poprawne liczby); opcjonalnie raport lokalnego modelu językowego (offline).
- Grafika: zrzut zakładki **Prognoza** (kafelki + wykres jutra).

### Slajd 8 – Wartość i dalsze kroki
- **Zakup energii na dobę naprzód** i planowanie: wiemy, kiedy szczyt (np. 21:00) i ile kWh.
- Dni, w których zużycie mocno przekracza prognozę przy słabym deszczu = **kandydaci na wody obce / nieszczelności**
  (mamy gotowy moduł anomalii: zespół 3 modeli, na alarmach tłoczni trafia 2,6× częściej niż losowo; powódź IX 2024
  wykryta na wszystkich pompowniach; PNB1 – wysoki przepływ nocny → infiltracja).
- Dalej: więcej pompowni, prognoza pogody z kilku modeli, integracja z SCADA, automatyczny raport dzienny.

---

## 3. Zrzuty ekranu do zrobienia (przed konkursem)

Uruchom `python main.py aplikacja`, ustaw okno przeglądarki ~1600 px szerokości, zrób zrzuty (Win+Shift+S):

| Zrzut | Gdzie | Ustawienia |
|---|---|---|
| kafelki + wykres wariantów | **Model** | – |
| doby suche vs mokre, ważność cech | **Model** | przewiń w dół |
| kafelki + opis + wykres jutra | **Prognoza** | plik `01_PZ1_8tyg_licznik_mock.csv`, RY_PZ1, Przygotuj |
| „Jak trafiały prognozy” | **Prognoza** | jw. |
| zużycie na tle deszczu | **Prognoza – szczegóły** | plik `09_CH_T_10tyg_licznik_mock.csv`, widok dobowo |
| panel z rozpoznanym plikiem | panel boczny | po „Wczytaj pliki” |

Wykresy Plotly mają w prawym górnym rogu ikonę aparatu – zapisuje PNG w wysokiej jakości.

---

## 4. Demo na żywo (~3 min)

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
