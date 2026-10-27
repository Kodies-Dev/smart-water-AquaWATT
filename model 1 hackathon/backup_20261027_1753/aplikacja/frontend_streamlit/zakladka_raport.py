"""
Zakladka Raport - generowanie opisu tekstowego anomalii przez lokalny LLM.

Generowanie idzie partiami, po jednej na przebieg skryptu. Dzieki temu
miedzy partiami interfejs odzywa i przycisk zatrzymania faktycznie dziala -
przy jednym dlugim wywolaniu Streamlit bylby zablokowany do konca.
"""

import streamlit as st

from backend_ml_llm.mistral_raport_generator import report_generator
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.pola import Pola


def renderuj():
    st.subheader("Raport tekstowy (lokalny LLM)")

    if st.session_state.result_df is None:
        st.info("Najpierw uruchom detekcje w zakladce 'Detekcja'.")
        return

    res = st.session_state.result_df
    n_anom = int(res["Anomaly_Final"].sum())

    if n_anom == 0:
        st.info("Nie wykryto anomalii - nie ma z czego zrobic raportu.")
        return

    models = Narzedzia.get_ollama_models()
    if not models:
        st.warning(
            "Nie wykryto Ollamy na http://localhost:11434. "
            "Uruchom `ollama serve` i sciagnij model (`ollama pull qwen3:8b`)."
        )
        models = ["qwen3:8b", "mistral-nemo", "mistral"]

    c1, c2 = st.columns(2)
    with c1:
        model = st.selectbox("Model", models, key="model_raport")
    with c2:
        partia = Pola.num_field("Anomalii na partie", 1, 100, 10, 1, "partia",
                                help="Raport powstaje partiami. Po kazdej partii mozna "
                                     "przerwac - im mniejsza partia, tym szybciej "
                                     "zadziala przycisk zatrzymania.")

    st.caption(f"Raport obejmie wszystkie {n_anom} wykrytych anomalii, "
               f"posortowanych wg liczby glosow i liczby flag outlier.")

    anomalie = (res[res["Anomaly_Final"] == 1]
                .sort_values(["Anomaly_Votes", "Has_Outlier"], ascending=False))

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Generuj raport", type="primary",
                     disabled=st.session_state.gen_trwa):
            st.session_state.gen_trwa = True
            st.session_state.gen_indeks = 0
            st.session_state.gen_czesci = []
            st.session_state.gen_model = model
            st.session_state.report = None
            st.rerun()
    with b2:
        if st.button("Zatrzymaj", disabled=not st.session_state.gen_trwa):
            st.session_state.gen_trwa = False
            st.session_state.report = "\n\n".join(st.session_state.gen_czesci)
            st.rerun()

    if st.session_state.gen_trwa:
        i = st.session_state.gen_indeks
        paczka = anomalie.iloc[i:i + int(partia)]

        st.progress(min(i / n_anom, 1.0),
                    text=f"Opisano {i} z {n_anom} anomalii...")

        if len(paczka) == 0:
            st.session_state.gen_trwa = False
            st.session_state.report = "\n\n".join(st.session_state.gen_czesci)
            st.rerun()
        else:
            try:
                czesc = report_generator.generate_report(
                    paczka, model=st.session_state.gen_model)
                st.session_state.gen_czesci.append(czesc)
                st.session_state.gen_indeks = i + int(partia)
                st.rerun()
            except Exception as e:
                st.session_state.gen_trwa = False
                st.error(f"Blad generowania raportu: {e}")

    if st.session_state.gen_czesci and not st.session_state.gen_trwa:
        opisano = min(st.session_state.gen_indeks, n_anom)
        if opisano < n_anom:
            st.warning(f"Generowanie przerwane. Opisano {opisano} z {n_anom} anomalii.")
        else:
            st.success(f"Gotowe. Opisano wszystkie {n_anom} anomalii.")

    if st.session_state.report:
        st.markdown("#### Raport")
        st.write(st.session_state.report)
        Narzedzia.przycisk_pobierania(
            "Pobierz raport (TXT)", st.session_state.report.encode("utf-8"),
            "raport_anomalie.txt", "text/plain", key="pob_raport")