"""Zakladka Jak czytac wyniki - poradnik do prognozy energii. Czysty tekst, zero logiki."""

import streamlit as st


def renderuj():
    st.subheader("Dobre praktyki – dane i wyniki prognozy")
    with st.expander("0. Jak przygotowac plik do prognozy", expanded=True):
        st.markdown("""
- **Co najmniej ok. 5 tygodni** godzinowego (albo gestszego) zuzycia energii - model patrzy na zuzycie dobe, tydzien
  i dwa tygodnie wczesniej oraz na typowy profil z 4 tygodni. Dla pompowni z bazy krotszy plik wystarczy
  (wczesniejsze tygodnie dobieramy z bazy).
- **Formaty:** odczyty licznika `data;godzina;typ;wartosc;status` (jak pliki `mock_*` - przyrosty liczymy sami,
  reset/wymiana licznika jest rozpoznawana), raport dystrybutora `Rap_godzinowy_*.csv`, albo dwie kolumny `czas;kwh`.
- **Czas lokalny** (polski, ze zmiana czasu) - tak jak w plikach z liczników. W formacie `czas;kwh` czas oznacza
  **poczatek godziny** (jesli koniec - zaznacz to w zakladce Szczegoly techniczne / CLI `--koniec-godziny`).
- Separator (`;` `,` tab) i kodowanie (UTF-8, Windows-1250) rozpoznajemy sami.
- **Braki w danych** (pojedyncze godziny, kilka dob) nie przeszkadzaja - takie doby po prostu nie wchodza do oceny.
- **Wybierz wlasciwa pompownie** w panelu - nazwa z bazy (np. RY_PZ1) daje dluzsza historie; nowa pompownia
  dostaje model ogolny (przenosi sie dobrze - sprawdzone na Rybniku).
""")
    with st.expander("1. Co prognozujemy", expanded=True):
        st.markdown("""
**Zuzycie energii elektrycznej [kWh] przez pompownie sciekow w kazdej godzinie nastepnej doby.**
Prognoza dobowa i miesieczna to suma godzinowa. Model korzysta tylko z tego, co jest znane dobe wczesniej:
historii zuzycia, kalendarza (swieta, ferie, wakacje), opadu i pogody do chwili prognozy oraz **prognozy pogody
wydanej dzien wczesniej** (Open-Meteo).
""")
    with st.expander("2. Miary bledu"):
        st.markdown("""
- **WAPE** = suma |bledow| / suma zuzycia. 10% oznacza, ze przecietnie mylimy sie o 10% zuzycia.
  Dobowe liczone z pelnych dob, godzinowe z kazdej godziny (zawsze wieksze - pojedyncze godziny sa bardziej losowe).
- **Bias** - czy model systematycznie zawyza (+) czy zaniza (-) sume. Model celuje w mediane, wiec na pompowniach
  z gwaltownymi szczytami po ulewach lekko zaniza sumy.
- **Proste reguly** do porownania: *wczoraj o tej godzinie*, *tydzien temu*, *mediana z 4 tygodni*. Model ma sens,
  jesli jest od nich wyraznie lepszy.
""")
    with st.expander("3. Backtest i uczciwy backtest"):
        st.markdown("""
**Backtest** - dla kazdej doby w pliku liczymy prognoze tak, jakby byla wydana dzien wczesniej, i porownujemy
z rzeczywistoscia. **Uwaga:** zapisany model widzial w treningu wszystkie dane z bazy. Jesli plik obejmuje ten
okres, wynik bylby zawyzony - aplikacja to pokaze. **Uczciwy backtest** trenuje model od nowa bez okresu z pliku
(1-2 min), czyli sprawdza go na danych, ktorych nie znal.
""")
    with st.expander("4. Formaty plikow w zakladce Prognoza"):
        st.markdown("""
Rozpoznawane automatycznie:
- **licznik narastajacy** `data;godzina;typ;wartosc;status` (jak pliki `mock_*`) - przyrosty liczone jak w ETL,
- **raport dystrybutora** jak `Rap_godzinowy_*.csv` (znacznik = koniec godziny),
- **prosty** `czas;kwh` - czas lokalny = poczatek godziny (albo zaznacz *koniec godziny*).

Model potrzebuje ok. **5 tygodni historii**. Dla pompowni z bazy (np. RY_PZ1) wczesniejsze tygodnie sa dociagane
z bazy; nowa pompownia musi miec je w pliku.
""")
    with st.expander("5. Gdzie model sie myli"):
        st.markdown("""
W **suche doby** blad jest maly (kilka procent). Najwiekszy blad jest w **doby z ulewa** - zuzycie rosnie przez wody
opadowe, a prognoza deszczu sprzed doby nie zawsze trafia. Z idealna prognoza pogody blad bylby wyraznie mniejszy -
to pokazuje zakladka *Wyniki modeli*.
""")
