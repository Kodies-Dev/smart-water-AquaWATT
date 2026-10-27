"""Zakladka Zalecenia dla uzytkownika - wymagania dotyczace danych, metodyka prognozy i anomalii, ograniczenia. Czysty tekst, zero logiki."""

import streamlit as st


def renderuj():
    st.subheader("Zalecenia dla użytkownika")
    with st.expander("Wymagania dotyczące danych", expanded=True):
        st.markdown("""
- **Zakres:** co najmniej ok. 5 tygodni danych godzinowych (lub gęstszych). Dla pomp znanych w modelu (np. RY_PZ1) wystarczy krótszy plik.
- **Formaty** (rozpoznawane automatycznie):
  - odczyty narastające licznika `data;godzina;typ;wartosc;status` – przyrosty są liczone automatycznie, resety i wymiany licznika wykrywane,
  - raport dystrybutora `Rap_godzinowy_*.csv` – znacznik czasu oznacza koniec godziny,
  - `czas;kwh` – czas lokalny, początek godziny.
- **Separator i kodowanie** (UTF-8, Windows-1250) są wykrywane automatycznie; w razie potrzeby można je wskazać w panelu bocznym.
- **Czas:** lokalny (Europe/Warsaw), ze zmianą czasu.
- **Braki:** pojedyncze godziny i krótkie luki są dopuszczalne; niepełne doby nie wchodzą do oceny dokładności.
- **Pompownia:** wybierana w panelu. Nowa pompownia korzysta z modelu ogólnego i wymaga pełnej historii w pliku.
""")
    with st.expander("Prognoza zużycia energii"):
        st.markdown("""
- **Przedmiot prognozy:** zużycie energii [kWh] w każdej godzinie kolejnej doby. Sumy dobowe i miesięczne są agregowane z wartości godzinowych.
- **Zmienne modelu:** historia zużycia, kalendarz (święta, ferie, wakacje), pogoda zmierzona oraz prognoza pogody wydana dzień wcześniej (D-1, Open-Meteo).
- **Horyzonty:** jutro (24 h) · tydzień (7 dni, osobny model dla każdego dnia) · plan na 2 miesiące (model dobowy z przedziałem P10–P90).
- **WAPE** = Σ|błąd| / Σ zużycia. Wartość dobowa jest liczona z pełnych dób; godzinowa jest zawsze wyższa.
- **Bias:** systematyczne zawyżanie (+) lub zaniżanie (−) sumy.
- **Metody referencyjne:** „jak wczoraj”, „jak tydzień temu”, mediana z 4 tygodni. Model jest uzasadniony, gdy wyraźnie je przewyższa.
""")
    with st.expander("Walidacja (backtest)"):
        st.markdown("""
- **Backtest:** dla każdej doby z pliku prognoza jest liczona wyłącznie z danych znanych w D-1, a następnie porównywana z wartością rzeczywistą.
- **Uczciwy backtest:** jeśli plik pokrywa się z okresem treningu, wynik byłby zawyżony – aplikacja sygnalizuje to ostrzeżeniem.
  Wariant uczciwy trenuje model od nowa bez okresu z pliku (1–2 min) i ocenia go na danych, których model nie widział.
""")
    with st.expander("Wody przypadkowe i anomalie"):
        st.markdown("""
- **Baza bezdeszczowa:** typowy przepływ lub zużycie energii w suche dni (ten sam dzień tygodnia, ostatnie tygodnie).
- **Zdarzenie:** kilka kolejnych godzin z nadwyżką ponad bazę; typ („dopływ opadowy”, „po opadach”, „bez opadu”) wynika z opadu w trakcie zdarzenia i przed nim.
- **Infiltracja:** udział przepływu nocnego w średnim przepływie doby w dni suche. **Dopływ opadowy:** nadwyżka przepływu na 1 mm opadu.
- **Anomalie ML:** Isolation Forest, LOF i One-Class SVM; doba jest uznana za nietypową, gdy wskazuje ją co najmniej 2 z 3 modeli.
""")
    with st.expander("Ograniczenia"):
        st.markdown("""
- **Dni z intensywnym opadem** mają największy błąd – ograniczeniem jest trafność prognozy opadu. Porównanie dób suchych i mokrych: zakładka **Model**.
- **Plan na 2 miesiące** opiera się na typowej pogodzie dla pory roku; służy do planowania budżetu i zakupu energii, nie do prognoz godzinowych.
""")
