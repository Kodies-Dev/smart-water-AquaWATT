"""
Zakladka Dobre praktyki - poradnik wbudowany w aplikacje. Czysty tekst,
zero logiki - stad jeden dlugi renderuj() zamiast dzielenia na funkcje.
"""

import streamlit as st


def renderuj():
    st.subheader("Dobre praktyki i interpretacja wynikow")

    with st.expander("1. Jak przygotowac plik CSV przed wgraniem", expanded=True):
        st.markdown("""
**Posortuj dane chronologicznie.** To najwazniejsza rzecz. Aplikacja traktuje kolejnosc
wierszy jako kolejnosc w czasie - srednie kroczace i roznice miedzy wierszami licza sie
wzgledem sasiadow w pliku. Na danych posortowanych losowo te cechy beda szumem, a nie
sygnalem. Jesli masz kolumne z data lub znacznikiem czasu, posortuj po niej przed
zapisaniem pliku.

**Usun kolumny-identyfikatory.** Numery porzadkowe, ID transakcji, numery klienta - to
liczby, wiec aplikacja potraktuje je jako kolumny numeryczne i policzy dla nich z-score
oraz srednie kroczace. Wynik jest bezuzyteczny (rosnacy licznik zawsze wyglada jak
idealny trend), a dodatkowo takie kolumny psuja modele, bo wnosza do nich sztuczny
wymiar. Jesli musisz zachowac identyfikator do pozniejszego dopasowania wynikow,
zamien go na tekst - kolumny tekstowe sa pomijane w obliczeniach, ale zostaja w tabeli
wynikowej i w eksporcie CSV.

**Sprawdz separator i format liczb.** Aplikacja pozwala wybrac separator kolumn
(przecinek, srednik, tabulator, pionowa kreska), ale separator dziesietny musi byc
kropka. Plik z liczbami w formacie `1 234,56` zostanie wczytany jako tekst i kolumna
wypadnie z analizy.

**Zdecyduj co zrobic z brakami danych.** Puste komorki sa wypelniane zerem przed
podaniem do modeli. Jesli zero jest w twoich danych sensowna wartoscia (na przyklad
kwota), braki zostana potraktowane jako prawdziwe zera i moga zaburzyc wynik. Lepiej
uzupelnic je swiadomie przed wgraniem albo usunac takie wiersze.

**Jedna tabela, jeden typ zdarzenia.** Nie laczaj w jednym pliku danych o roznej
charakterystyce (na przyklad transakcji detalicznych i hurtowych). Modele ucza sie
"co jest normalne" z calego zbioru naraz - wymieszanie dwoch rozkladow sprawi, ze
mniejszy z nich w calosci zostanie uznany za anomalie.

**Minimalny rozmiar.** Ponizej okolo 100 wierszy wyniki sa malo wiarygodne. LOF
porownuje gestosc z sasiadami, a przy kilkudziesieciu punktach kazdy jest sasiadem
kazdego. Kwartyle do flag IQR tez sa wtedy bardzo niestabilne.
        """)

    with st.expander("2. Kolejnosc pracy w aplikacji"):
        st.markdown("""
**Krok 1 - zakladka Dane.** Zanim cokolwiek policzysz, sprawdz czy plik wczytal sie
poprawnie. Zwroc uwage na liczbe kolumn numerycznych - jesli jest mniejsza niz
oczekujesz, ktoras kolumna zostala wczytana jako tekst (zwykle przez przecinek
dziesietny albo spacje w liczbach). Sprawdz tez braki danych.

**Krok 2 - zakladka Wykresy.** Obejrzyj dane przed detekcja. Histogram pokaze ci
ksztalt rozkladu, boxplot od razu ujawni wartosci skrajne, a wykres liniowy pokaze
czy dane maja jakis trend lub sezonowosc. Na tym etapie czesto widac oczywiste bledy
danych - ujemne kwoty, niemozliwe wieki, wartosci sto razy wieksze od reszty.

**Krok 3 - zakladka Detekcja.** Ustaw parametry i uruchom. Zacznij od wartosci
domyslnych, potem doreguluj.

**Krok 4 - zakladka Anomalie.** Sprawdz czy wynik ma sens. To najwazniejszy etap
weryfikacji - opisany nizej.

**Krok 5 - zakladka Raport.** Dopiero gdy wyniki wygladaja sensownie, generuj opis
tekstowy. Generowanie trwa najdluzej z calego procesu, wiec nie ma sensu robic tego
na parametrach, ktore i tak bedziesz zmieniac.
        """)

    with st.expander("3. Jak dobrac parametry"):
        st.markdown("""
**Okno sredniej kroczacej.** Okresla, jak dlugi fragment historii jest traktowany jako
"lokalna norma". Male okno (5-10) reaguje szybko na zmiany i wychwytuje nagle skoki.
Duze okno (50-200) wygladza dane i pokazuje odstepstwa od dluzszego trendu. Jesli twoje
dane maja naturalny cykl - na przyklad dobowy albo tygodniowy - warto ustawic okno
zblizone do dlugosci tego cyklu.

**Oczekiwany odsetek anomalii.** To zalozenie, nie wynik pomiaru. Modele przytna wynik
dokladnie na tym progu, wiec przy 0.05 kazdy z nich wskaze okolo 5 procent wierszy -
nawet jesli dane sa idealnie czyste. Zacznij od 0.05, obejrzyj wykres z-score
w zakladce Anomalie i doreguluj:

- oznaczone anomalie maja z-score bliski zeru - obniz parametr, model dopycha wynik
  do zadanego procentu z normalnych wierszy
- cos ewidentnie odstajacego zostalo pominiete - podnies parametr

Dla wykrywania oszustw realistyczne wartosci to 0.01-0.02, bo prawdziwe naduzycia sa
rzadkie. Dla wykrywania bledow w danych czy awarii czujnikow moze byc wyzej.

**Szybki SVM.** Domyslnie wylaczony i w wiekszosci przypadkow warto tak zostawic.
Wariant przyblizony jest niestabilny - w testach na jednym zbiorze wykryl zero
anomalii, podczas gdy pozostale dwa modele wskazaly po 25, a na innym ponad dwa
razy za duzo. Model, ktory wskaze zero wierszy, w praktyce wypada z glosowania
i wynik opiera sie na dwoch modelach zamiast trzech.

Na malych plikach wariant dokladny jest rownie szybki (0,13 sekundy wobec 0,15
przy 500 wierszach). Przy 50 tysiacach wierszy jest wolniejszy okolo dwa i pol
raza - 26 sekund wobec 10 - co nadal mozna zaakceptowac. Wlacz szybki wariant
dopiero wtedy, gdy detekcja trwa niewygodnie dlugo, i sprawdz wtedy w zakladce
Anomalie, czy zaden model nie wypadl z glosowania.
        """)

    with st.expander("4. Jak czytac wyniki - zakladka Detekcja"):
        st.markdown("""
**Metryki per model.** Cztery liczby pod przyciskiem detekcji pokazuja, ile wierszy
wskazal kazdy model osobno i ile przeszlo finalne glosowanie.

Jesli jeden model wskazuje radykalnie wiecej niz pozostale, to sygnal ze wykryl cos
innego niz reszta - nie ze sie myli. Kazdy z trzech patrzy na dane inaczej:

- **Isolation Forest** szuka punktow, ktore latwo oddzielic od reszty losowymi
  podzialami. Dobrze radzi sobie z wartosciami skrajnymi w pojedynczych kolumnach.
- **LOF** porownuje lokalna gestosc punktu z gestoscia jego sasiadow. Wychwytuje
  anomalie kontekstowe - wartosc sama w sobie zwyczajna, ale nietypowa w swoim
  otoczeniu.
- **One-Class SVM** rysuje granice wokol obszaru uznanego za normalny. Reaguje na
  ogolny ksztalt rozkladu.

**Finalna liczba jest zwykle mniejsza niz pozostale trzy.** To normalne i zamierzone -
wymaga zgody przynajmniej dwoch modeli, wiec odsiewa przypadki, ktore tylko jeden
uznal za podejrzane.

**Tabela anomalii.** Kolumna `Anomaly_Votes` mowi ile modeli zaglosowalo (2 albo 3).
Wiersze z trzema glosami sa pewniejsze. Kolumna `Has_Outlier` mowi w ilu kolumnach
wiersz jest jednoczesnie statystycznym outlierem IQR - wysoka wartosc oznacza, ze
wiersz odstaje na wielu wymiarach naraz.
        """)

    with st.expander("5. Jak czytac wyniki - zakladka Anomalie"):
        st.markdown("""
**Wykres glosow modeli.** Sluzy do oceny, czy modele sie ze soba zgadzaja. Podobne
slupki oznaczaja spojna ocene danych. Jeden slupek wyraznie wyzszy oznacza, ze ten
model jest bardziej czuly na charakterystyke twoich danych - warto wtedy sprawdzic,
ktore wiersze wskazuje tylko on.

**Glowna przyczyna anomalii wg kolumny.** Pokazuje, w ktorej kolumnie najczesciej lezy
zrodlo problemu (kolumna o najwyzszej wartosci bezwzglednej z-score w danym wierszu).
Jesli jedna kolumna zdecydowanie dominuje, warto sie zastanowic, czy to naprawde
anomalie, czy po prostu ta kolumna ma inna skale albo rozklad niz reszta.

**Wykres sredniej kroczacej.** Najbardziej intuicyjny obraz. Niebieska linia to
wartosci, zielona przerywana to lokalna norma, czerwone kwadraty to anomalie. Szukaj
miejsc, gdzie niebieska linia gwaltownie odrywa sie od zielonej. Jesli czerwone punkty
leza tam, gdzie obie linie ida rownolegle - model prawdopodobnie zareagowal na inna
kolumne niz aktualnie ogladana.

**Wykres z-score.** Pokazuje, jak bardzo wartosci odstaja od sredniej calej kolumny,
w jednostkach odchylenia standardowego. Przerywane linie to prog, domyslnie 3.

Na co zwrocic uwage:

- czerwone punkty **powyzej progu** - anomalie potwierdzone tez statystycznie,
  najpewniejsze przypadki
- czerwone punkty **przy zerze** - model wykryl je z innego powodu niz wartosc w tej
  kolumnie, sprawdz inne kolumny w liscie rozwijanej
- **wszystkie punkty scisniete przy zerze, jeden bardzo wysoko** - klasyczny objaw
  pojedynczej ekstremalnej wartosci, ktora zawyzyla odchylenie standardowe i przez to
  splaszczyla z-score wszystkich pozostalych wierszy

**Uwaga o roznicy miedzy z-score a flaga IQR.** Wartosc moze miec bardzo wysoki
z-score, a mimo to nie byc oznaczona jako outlier IQR - albo odwrotnie. To nie blad.
Z-score opiera sie na sredniej i odchyleniu standardowym, ktore sa wrazliwe na
pojedyncze skrajne wartosci. IQR opiera sie na kwartylach, ktore sa na nie odporne.
Rozbieznosc miedzy tymi dwiema miarami sama w sobie jest informacja.
        """)

    with st.expander("6. Jak czytac raport tekstowy"):
        st.markdown("""
**Wszystkie liczby w raporcie sa liczone w Pythonie, nie przez model jezykowy.** Model
dostaje gotowe fakty i ma je tylko sformulowac w plynne zdania. To swiadoma decyzja
projektowa - male modele lokalne mylily numeracje wierszy i przypisywaly wartosci do
zlych kolumn, gdy dostawaly do analizy surowa tabele.

W praktyce oznacza to, ze **liczbom w raporcie mozna ufac**, natomiast sformulowania
moga sie roznic miedzy modelami i uruchomieniami.

**Raport obejmuje wszystkie wykryte anomalie**, generowane partiami z mozliwoscia
przerwania - kazda anomalia to osobny tekst do wygenerowania, a przy setkach wierszy
trwaloby to dlugo w jednym ciagu.
        """)

    with st.expander("7. Czego aplikacja nie robi"):
        st.markdown("""
**Nie odrozni bledu danych od prawdziwej anomalii.** Wiek 999 i nietypowo duza
transakcja beda potraktowane tak samo - jako wartosci odstajace. Rozroznienie wymaga
wiedzy o dziedzinie i nalezy do ciebie.

**Nie wie, co jest wazne w twoich danych.** Modele nie maja pojecia, ze kolumna
z kwota jest istotniejsza niz kolumna z numerem tygodnia. Wszystkie kolumny numeryczne
traktowane sa rownorzednie - dlatego warto usunac przed wgraniem te, ktore nie niosa
informacji.

**Nie wykrywa anomalii, ktorych nie widac w liczbach.** Jesli oszustwo polega na
zwyklej kwocie o zwyklej porze, ale na koncie nalezacym do kogos innego, zadne z tych
narzedzi tego nie zauwazy.

**Nie zastepuje weryfikacji przez czlowieka.** Wynik to lista wierszy do sprawdzenia,
a nie werdykt. Czesc wskazan zawsze bedzie falszywymi alarmami - to wpisane w sposob
dzialania tych metod, nie usterka.
        """)