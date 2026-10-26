"""
Zakladka Anomalie - wykresy wynikow detekcji pod siec kanalizacyjna: os czasu pompowni (rzeczywiste vs baza
bezdeszczowa, opad, anomalie wg typu), ranking wod obcych, glowne przyczyny, oraz wykresy z Detektora GUS
(glosy modeli, glowna przyczyna wg kolumny, szeregi wedlug jednostek, z-score).
"""

import streamlit as st

from frontend_streamlit.pola import Pola
from frontend_streamlit.styles import ZSCORE_HELP
from frontend_streamlit.wykresy import Wykresy


def renderuj():
    st.subheader("Wykresy anomalii")

    res = st.session_state.result_df
    if res is None or "Anomaly_Final" not in res:
        st.info("Najpierw uruchom detekcje w zakladce 'Detekcja'.")
        return
    ex = st.session_state.get("anom_extra", {})
    num_cols = st.session_state.num_cols
    obiekty = sorted(res["obiekt_id"].unique())

    # --- os czasu jednej pompowni
    obiekt = st.selectbox("Pompownia", obiekty, key="anom_obiekt")
    lim_os = Pola.axis_fields("os_czasu")
    Wykresy.show(Wykresy.fig_os_czasu(res, obiekt, lim_os))
    st.caption("Najedz na kwadrat, zeby zobaczyc opis anomalii: typ, glowna przyczyna, skala, opad i ktore modele "
               "zaglosowaly. Zielona przerywana linia to baza bezdeszczowa - normalny przeplyw sciekow bytowych.")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        Wykresy.show(Wykresy.fig_typy(res))
    with c2:
        if ex.get("ranking") is not None and len(ex["ranking"]):
            Wykresy.show(Wykresy.fig_ranking(ex["ranking"]))
    if ex.get("ranking") is not None:
        st.dataframe(ex["ranking"].round(2), width="stretch")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if ex.get("przyczyny") is not None and len(ex["przyczyny"]):
            Wykresy.show(Wykresy.fig_przyczyny(ex["przyczyny"]))
    with c2:
        lim_votes = Pola.axis_fields("votes")
        Wykresy.show(Wykresy.fig_votes(res, lim_votes))

    st.divider()
    st.markdown("#### Szeregi wedlug pompowni (tryb panelowy)")
    col = st.selectbox("Kolumna do analizy", num_cols, key="anom_col",
                       format_func=lambda c: f"{c} - {ex.get('nazwy', {}).get(c, c)}" if ex.get("nazwy") else c)
    wybrane = st.multiselect("Pompownie na wykresie", obiekty, default=obiekty[:6], key="wybrane_jednostki")
    if wybrane:
        lim_panel = Pola.axis_fields("panel")
        Wykresy.show(Wykresy.fig_grupy(res, col, "obiekt_id", "dzien", wybrane, lim_panel))
    st.caption("Kazda linia to jedna pompownia. Skok pojedynczej linii to nagla zmiana, a linia biegnaca z dala "
               "od pozostalych tego samego dnia to odstawanie od innych - przy tej samej pogodzie.")

    thr = Pola.num_field("Prog z-score", 1.0, 6.0, 3.0, 0.5, "thr", is_int=False, help=ZSCORE_HELP)
    lim_z = Pola.axis_fields("zscore")
    Wykresy.show(Wykresy.fig_zscore_anom(res[res["obiekt_id"] == obiekt], col, thr, lim_z))
    st.caption(f"Z-score odporny (mediana, IQR) dla pompowni {obiekt}. " + ZSCORE_HELP)

    if ex.get("znane") is not None and len(ex["znane"]):
        st.divider()
        st.markdown("#### Znane zdarzenia")
        st.dataframe(ex["znane"], width="stretch")
