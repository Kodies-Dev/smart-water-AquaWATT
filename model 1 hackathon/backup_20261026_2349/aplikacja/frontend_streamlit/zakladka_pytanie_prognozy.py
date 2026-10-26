"""
Zakladka Pytanie - pytania o model prognozy i jego wyniki wlasnymi slowami. Model jezykowy dostaje policzone
fakty (jak w Detektorze GUS), nie surowa tabele.
"""

import streamlit as st

from backend_ml_llm.raport_prognozy import fakty, pytanie, wczytaj_wyniki
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.zakladka_raport_prognozy import _modele_llm


def renderuj():
    st.subheader("Zapytaj o model i prognoze")
    meta, met, _, _ = wczytaj_wyniki()
    f = fakty(meta, met, st.session_state.get("prog_wynik"))
    if not f.strip():
        st.info("Brak wynikow - uruchom `python main.py model` albo zrob prognoze w zakladce 'Prognoza'.")
        return
    model = _modele_llm("model_pytanie_prog")
    with st.expander("Co dokladnie widzi model"):
        st.text(f)
    st.session_state.setdefault("historia_prognozy", [])
    tresc = st.text_area("Pytanie", key="pytanie_prog", height=90,
                         placeholder="np. O ile model jest lepszy od prognozy 'wczoraj' i gdzie myli sie najbardziej?")
    c1, c2 = st.columns(2)
    with c1:
        zapytaj = st.button("Zapytaj", type="primary", key="zapytaj_prog")
    with c2:
        if st.button("Wyczysc historie", key="wyczysc_prog"):
            st.session_state.historia_prognozy = []
            st.rerun()
    if zapytaj and tresc.strip():
        with st.spinner(f"Model odpowiada ({model})..."):
            try:
                odp = pytanie(f, tresc, model, st.session_state.historia_prognozy)
                st.session_state.historia_prognozy.append((tresc, odp))
            except Exception as e:
                st.error(f"Blad: {e}")
    for p, o in reversed(st.session_state.historia_prognozy):
        st.markdown(f"**Pytanie:** {p}")
        st.write(o)
        st.divider()
