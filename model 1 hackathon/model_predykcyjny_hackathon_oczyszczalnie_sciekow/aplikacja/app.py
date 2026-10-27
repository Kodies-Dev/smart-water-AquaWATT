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
from frontend_streamlit import zakladka_wody_przypadkowe
from frontend_streamlit import zakladka_anomalie_klient
from frontend_streamlit import zakladka_anomalie_szczegoly
from frontend_streamlit import zakladka_twoja_prognoza
from frontend_streamlit import zakladka_prognoza_szczegoly
from frontend_streamlit import zakladka_model
from frontend_streamlit import zakladka_raport_prognozy
from frontend_streamlit import zakladka_pytanie_prognozy
from frontend_streamlit import zakladka_jak_czytac

# Glowny temat konkursu (odpowiedz organizatorow): WODY PRZYPADKOWE, drugi: prognoza energii w korelacji z opadem.
# Anomalie maja widok dla klienta i szczegoly (jak prognoza). Techniczne zakladki z Detektora GUS (Detekcja anomalii,
# Anomalie (GUS)) - tylko z POKAZ_ANOMALIE_GUS=1.
POKAZ_ANOMALIE = os.environ.get("POKAZ_ANOMALIE_GUS") == "1"

st.set_page_config(page_title="Hydro-analityka", page_icon=None, layout="wide")

Wyglad.zastosuj()  # aplikujemy style
MagazynDanych.inicjalizuj()

# baza po ETL wczytuje sie sama przy pierwszym otwarciu (klient nie musi nic klikac); przycisk w panelu odswieza
if not st.session_state.get("baza_proba"):
    st.session_state.baza_proba = True
    try:
        from backend_ml_llm.nasz_detektor import nasz_detektor
        with st.spinner("Ładowanie danych referencyjnych..."):
            st.session_state.d_baza, st.session_state.alarmy = nasz_detektor.dane_z_bazy()
    except Exception:
        pass                                         # bez bazy: komunikat ponizej

panel_prognozy.renderuj()


# ---------------------------------------------------------------- main

st.title("Hydro-analityka")
st.caption("Wykrywanie anomalii i wód przypadkowych oraz prognozowanie zużycia energii w przepompowniach")

if st.session_state.get("d_baza") is None:
    st.warning("Dane referencyjne (pogoda, kalendarz) nie zostały załadowane. Odśwież stronę.")
if not st.session_state.zbiory:
    st.info("Wgraj plik CSV w panelu bocznym, aby rozpocząć.")
    st.stop()  # zatrzymuje dalsze wykonanie skryptu


class _Grupa:
    """Grupa tematyczna: zakladka glowna z podzakladkami."""
    def __init__(self, *czesci):
        self.czesci = list(czesci)

    def renderuj(self):
        for tab, (_, modul) in zip(st.tabs([n for n, _ in self.czesci]), self.czesci):
            with tab:
                modul.renderuj()


# kolejnosc pracy: dane -> wody przypadkowe i anomalie -> prognoza energii -> raporty i dokumentacja
wody_anomalie = _Grupa(("Wody przypadkowe", zakladka_wody_przypadkowe), ("Anomalie", zakladka_anomalie_klient),
                       ("Szczegóły anomalii", zakladka_anomalie_szczegoly))
if POKAZ_ANOMALIE:
    from frontend_streamlit import zakladka_detekcja, zakladka_anomalie
    wody_anomalie.czesci += [("Detekcja anomalii (GUS)", zakladka_detekcja), ("Anomalie (GUS)", zakladka_anomalie)]
zakladki = [("Dane", _Grupa(("Zbiory", zakladka_dane), ("Wykresy", zakladka_wykresy))),
            ("Wody i anomalie", wody_anomalie),
            ("Prognoza energii", _Grupa(("Prognoza", zakladka_twoja_prognoza), ("Szczegóły prognozy", zakladka_prognoza_szczegoly),
                                        ("Model", zakladka_model))),
            ("Raporty", _Grupa(("Raport", zakladka_raport_prognozy), ("Pytanie", zakladka_pytanie_prognozy))),
            ("Zalecenia dla użytkownika", zakladka_jak_czytac)]      # ostatnia zakladka - wyrozniona w CSS (styles.py)

for tab, (_, modul) in zip(st.tabs([n for n, _ in zakladki]), zakladki):
    with tab:
        modul.renderuj()
