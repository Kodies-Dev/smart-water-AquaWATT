"""
Zakladka Model - jak dobry jest model (wyniki eksperymentow) + informacje o zapisanym modelu i jego trening
(przeniesione ze starej zakladki technicznej).
"""

import streamlit as st

from frontend_streamlit import zakladka_wyniki_modeli


def renderuj():
    zakladka_wyniki_modeli.renderuj()
    st.divider()
    with st.expander("Zapisany model i trening"):
        import model.prognoza as P
        try:
            _, meta = P.wczytaj_model()
            st.markdown(f"""
- **Model:** {meta['wariant']} (XGBoost), {meta['drzew']} drzew, horyzont {meta['horyzont_h']} h
- **Trening:** {f"{meta['godzin']:,}".replace(",", " ")} godzin, pompownie {', '.join(meta['obiekty'])}, dane {meta['dane_od'][:10]} – {meta['dane_do'][:10]}
- **Średni błąd dobowy na walidacji** (ostatnie 10% czasu każdej pompowni): {meta['wape_doba_walidacja']}%
- **Wytrenowany:** {meta['wytrenowano'][:16].replace('T', ' ')}
""")
        except FileNotFoundError:
            st.warning("Brak zapisanego modelu.")
        st.caption("Trening na wszystkich danych z bazy trwa 1-2 min. Potrzebny po ponownym ETL albo gdy modelu nie ma.")
        if st.button("Wytrenuj model na wszystkich danych z bazy", key="model_trenuj"):
            d = st.session_state.get("d_baza")
            if d is None:
                st.error("Brak danych z bazy.")
            else:
                with st.spinner("Trening..."):
                    P.trenuj(d)
                st.rerun()
