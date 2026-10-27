"""
Zakladka Pytanie - mozna zapytac model o wczytany zbior danych wlasnymi
slowami. Model dostaje policzony kontekst (statystyki, wyniki detekcji),
nie surowa tabele - patrz mistral_raport_generator.py po szczegoly.
"""

import streamlit as st

from frontend_streamlit.magazyn_danych import MagazynDanych
from backend_ml_llm.mistral_raport_generator import report_generator
from frontend_streamlit.narzedzia import Narzedzia


def renderuj():
    st.subheader("Zapytaj model o dane")

    if not st.session_state.zbiory:
        st.info("Najpierw wgraj plik CSV.")
        return

    models = Narzedzia.get_ollama_models()
    if not models:
        st.warning(
            "Nie wykryto Ollamy na http://localhost:11434. "
            "Uruchom `ollama serve` i sciagnij model (`ollama pull qwen3:8b`)."
        )
        models = ["qwen3:8b", "mistral-nemo", "mistral"]

    model_q = st.selectbox("Model", models, key="model_pytanie")

    # jesli detekcja byla zrobiona, model dostaje tez informacje o anomaliach
    df_q = st.session_state.result_df if st.session_state.result_df is not None else MagazynDanych.aktywny_df()
    num_cols_q = st.session_state.num_cols

    if st.session_state.result_df is None:
        st.caption("Detekcja nie zostala jeszcze uruchomiona - model widzi tylko "
                   "strukture i statystyki danych, bez informacji o anomaliach.")
    else:
        st.caption("Model widzi strukture danych, statystyki oraz wyniki detekcji anomalii.")

    with st.expander("Co dokladnie widzi model"):
        st.text(report_generator.build_data_context(df_q, num_cols_q))
        st.caption(
            "Model nie dostaje surowej tabeli, tylko powyzszy opis. Wszystkie liczby sa "
            "policzone w Pythonie, wiec nie moze ich przekrecic. Nie zna natomiast "
            "wartosci pojedynczych wierszy spoza listy najsilniejszych anomalii."
        )

    pytanie = st.text_area(
        "Pytanie",
        placeholder="np. Ktora kolumna najczesciej powoduje anomalie i jak silne sa odchylenia?",
        key="pytanie",
        height=90,
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        zapytaj = st.button("Zapytaj", type="primary")
    with c2:
        if st.button("Wyczysc historie"):
            st.session_state.historia_pytan = []
            st.rerun()

    if zapytaj:
        if not pytanie.strip():
            st.error("Wpisz pytanie.")
        else:
            with st.spinner(f"Model odpowiada ({model_q})..."):
                try:
                    odp = report_generator.ask_about_data(
                        df_q, pytanie, num_cols_q, model=model_q,
                        historia=st.session_state.historia_pytan,
                    )
                    st.session_state.historia_pytan.append((pytanie, odp))
                except Exception as e:
                    st.error(f"Blad: {e}")

    if st.session_state.historia_pytan:
        st.markdown("#### Rozmowa")
        for pyt, odp in reversed(st.session_state.historia_pytan):  # najnowsze na gorze
            st.markdown(f"**Pytanie:** {pyt}")
            st.write(odp)
            st.divider()

        rozmowa_txt = "\n\n".join(
            f"PYTANIE: {p}\n\nODPOWIEDZ: {o}" for p, o in st.session_state.historia_pytan)
        Narzedzia.przycisk_pobierania(
            "Pobierz rozmowe (TXT)", rozmowa_txt.encode("utf-8"),
            "pytania_o_dane.txt", "text/plain", key="pob_rozmowa")