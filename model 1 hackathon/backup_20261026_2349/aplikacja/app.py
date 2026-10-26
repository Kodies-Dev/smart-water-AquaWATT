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
from frontend_streamlit import panel_boczny
from frontend_streamlit import zakladka_dane
from frontend_streamlit import zakladka_wykresy
from frontend_streamlit import zakladka_twoja_prognoza
from frontend_streamlit import zakladka_wyniki_modeli
from frontend_streamlit import zakladka_prognoza
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
        MagazynDanych.dodaj("baza_dobowo", nasz_detektor.dobowo_do_podgladu(st.session_state.d_baza))
    except Exception:
        pass                                         # bez bazy: komunikat ponizej, mozna wgrac plik w panelu

panel_boczny.renderuj()


# ---------------------------------------------------------------- main

st.title("Prognoza zuzycia energii pompowni sciekow")

if not st.session_state.zbiory:
    st.info("Wczytaj dane z bazy (po ETL) albo wgraj plik CSV w panelu po lewej, zeby zaczac.")
    st.stop()  # zatrzymuje dalsze wykonanie skryptu

# kolejnosc: najpierw widok dla klienta, potem szczegoly techniczne
zakladki = [(" Twoja prognoza", zakladka_twoja_prognoza), (" Wyniki modeli", zakladka_wyniki_modeli),
            (" Prognoza (szczegoly)", zakladka_prognoza), (" Raport", zakladka_raport_prognozy),
            (" Pytanie", zakladka_pytanie_prognozy), (" Dane", zakladka_dane), (" Wykresy", zakladka_wykresy),
            (" Jak czytac wyniki", zakladka_jak_czytac)]
if POKAZ_ANOMALIE:
    from frontend_streamlit import zakladka_detekcja, zakladka_anomalie
    zakladki[5:5] = [(" Detekcja anomalii", zakladka_detekcja), (" Anomalie", zakladka_anomalie)]

for tab, (_, modul) in zip(st.tabs([n for n, _ in zakladki]), zakladki):
    with tab:
        modul.renderuj()
