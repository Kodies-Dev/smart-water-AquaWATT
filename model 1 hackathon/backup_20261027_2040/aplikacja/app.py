"""
Punkt wejscia aplikacji. Caly kod jest teraz podzielony na moduly - ten
plik tylko je spina: ustawia strone, inicjalizuje stan, rysuje panel
boczny i przelacza miedzy zakladkami (prognoza energii).

    konkrerne logiki:
  styles.py            - kolory, CSS, wyglad wykresow
  pola.py              - pola liczbowe z przycinaniem, zakresy osi
  narzedzia.py         - CSV, Ollama, probkowanie
  wykresy.py           - wszystkie wykresy plotly
  magazyn_danych.py    - zarzadzanie wczytanymi zbiorami (session_state)
  panel_boczny.py       - wgrywanie plikow
  zakladka_*.py         - kazda zakladka w osobnym pliku
  anomaly_d.py          - detekcja anomalii, cechy, modele ML
  mistral_raport_generator.py - warstwa LLM
"""

import streamlit as st
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# projekt hackathonu (model/, etl/, anomalie/) lezy poziom wyzej - stamtad bierzemy nasze modele
sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend_streamlit.magazyn_danych import MagazynDanych
from frontend_streamlit.styles import Wyglad
from frontend_streamlit import panel_prognozy          # panel_boczny.py z GUS zostaje, ten jest pod predykcje
from frontend_streamlit import zakladka_dane
from frontend_streamlit import zakladka_wykresy
from frontend_streamlit import zakladka_twoja_prognoza
from frontend_streamlit import zakladka_prognoza_szczegoly
from frontend_streamlit import zakladka_model
from frontend_streamlit import zakladka_raport_prognozy
from frontend_streamlit import zakladka_pytanie_prognozy
from frontend_streamlit import zakladka_jak_czytac

# Na razie aplikacja skupia sie na PREDYKCJI. Zakladki anomalii (Detekcja, Anomalie) sa schowane, nie usuniete:
# POKAZ_ANOMALIE=1 (zmienna srodowiskowa) albo True ponizej - wracaja.
POKAZ_ANOMALIE = os.environ.get("POKAZ_ANOMALIE") == "1"

st.set_page_config(page_title="prognoza energii - pompownie sciekow", page_icon=None, layout="wide")

Wyglad.zastosuj()  # aplikujemy style
MagazynDanych.inicjalizuj()

# baza po ETL wczytuje sie sama przy pierwszym otwarciu (klient nie musi nic klikac); przycisk w panelu odswieza
if not st.session_state.get("baza_proba"):
    st.session_state.baza_proba = True
    try:
        from backend_ml_llm.nasz_detektor import nasz_detektor
        with st.spinner("Wczytuje dane z bazy..."):
            st.session_state.d_baza, st.session_state.alarmy = nasz_detektor.dane_z_bazy()
    except Exception:
        pass                                         # bez bazy: komunikat ponizej

panel_prognozy.renderuj()


# ---------------------------------------------------------------- main

st.title("Prognoza zuzycia energii pompowni sciekow")

if st.session_state.get("d_baza") is None:
    st.warning("Brak polaczenia z baza danych (historia, pogoda, kalendarz potrzebne do prognozy) - uruchom baze "
               "(docker compose up -d db) i odswiez strone.")
if not st.session_state.zbiory:
    st.info("Wgraj plik w panelu po lewej, zeby zaczac. Mozna wgrac kilka naraz.")
    st.stop()  # zatrzymuje dalsze wykonanie skryptu

# kolejnosc: dane (wczytane w panelu) -> ich wykresy -> prognoza -> szczegoly prognozy -> model -> raport, pytanie, praktyki
zakladki = [(" Dane", zakladka_dane), (" Wykresy", zakladka_wykresy), (" Prognoza", zakladka_twoja_prognoza),
            (" Prognoza – szczegoly", zakladka_prognoza_szczegoly), (" Model", zakladka_model),
            (" Raport", zakladka_raport_prognozy), (" Pytanie", zakladka_pytanie_prognozy),
            (" Dobre praktyki", zakladka_jak_czytac)]
if POKAZ_ANOMALIE:
    from frontend_streamlit import zakladka_detekcja, zakladka_anomalie
    zakladki[5:5] = [(" Detekcja anomalii", zakladka_detekcja), (" Anomalie", zakladka_anomalie)]   # przed Modelem

for tab, (_, modul) in zip(st.tabs([n for n, _ in zakladki]), zakladki):
    with tab:
        modul.renderuj()
