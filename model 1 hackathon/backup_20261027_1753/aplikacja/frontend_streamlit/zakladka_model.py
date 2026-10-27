"""
Zakladka Model - jak dobry jest model (wyniki eksperymentow) + informacje o zapisanym modelu i jego trening
(przeniesione ze starej zakladki technicznej).
"""

import streamlit as st

from frontend_streamlit import zakladka_wyniki_modeli


def _horyzont():
    from model.config import WYNIKI
    import pandas as pd
    p, q = WYNIKI / "horyzont.csv", WYNIKI / "dlugi.csv"
    if not p.exists() and not q.exists():
        st.caption("Ocena horyzontu: `python main.py horyzont` (1–7 dni) i `python main.py horyzont --dlugi` (plan 2 miesiące).")
        return
    st.markdown("#### Jak dokładna jest prognoza dalej w przyszłość")
    if p.exists():
        t = pd.read_csv(p)
        r = t[t["obiekt"] == "RAZEM"][["dni", "model", "jak_k_dni_temu", "profil_4tyg"]].rename(
            columns={"dni": "dni naprzód", "model": "nasz model [%]", "jak_k_dni_temu": "„jak K dni temu” [%]",
                     "profil_4tyg": "typowy dzień [%]"})
        if (WYNIKI / "horyzont.png").exists():
            st.image(str(WYNIKI / "horyzont.png"))
        st.dataframe(r.round(1), width="stretch", hide_index=True)
    if q.exists():
        st.markdown("**Plan na 2 miesiące** (średni błąd dobowy P50 i pokrycie przedziału P10–P90 na startach testowych)")
        st.dataframe(pd.read_csv(q).rename(columns={"dni": "dni naprzód", "model_p50": "nasz plan [%]",
                                                    "jak_ostatnie_4tyg": "„średnia z 4 tygodni” [%]", "rok_temu": "„rok temu” [%]",
                                                    "pokrycie_p10_p90": "pokrycie przedziału [%]"}).round(1),
                     width="stretch", hide_index=True)


def renderuj():
    zakladka_wyniki_modeli.renderuj()
    st.divider()
    _horyzont()
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
        d = st.session_state.get("d_baza")
        st.caption((f"Baza: {d['energia']['obiekt_id'].nunique()} pompowni, " + f"{len(d['energia']):,} godzin zużycia. ".replace(",", " "))
                   if d is not None else "Brak połączenia z bazą – uruchom `docker compose up -d db`.")
        if st.button("Odśwież dane z bazy", key="model_odswiez"):
            try:
                from backend_ml_llm.nasz_detektor import nasz_detektor
                with st.spinner("Wczytuję..."):
                    st.session_state.d_baza, st.session_state.alarmy = nasz_detektor.dane_z_bazy()
                st.session_state.zbiory["baza_dobowo"] = nasz_detektor.dobowo_do_podgladu(st.session_state.d_baza)
                st.rerun()
            except Exception as e:
                st.error(f"Nie udało się: {e}")
        st.caption("Trening na wszystkich danych z bazy trwa 1-2 min. Potrzebny po ponownym ETL albo gdy modelu nie ma.")
        if st.button("Wytrenuj modele 1–7 dni i plan 2 miesiące (kilka minut)", key="model_trenuj_dni"):
            d = st.session_state.get("d_baza")
            if d is None:
                st.error("Brak danych z bazy.")
            else:
                import model.dlugi as D
                pasek = st.progress(0.0, text="Trening...")
                for k in range(1, 8):
                    pasek.progress((k - 1) / 8, text=f"Model na {k} dni naprzód...")
                    P.trenuj(d, dni=k)
                pasek.progress(7 / 8, text="Plan na 2 miesiące...")
                D.trenuj(d)
                pasek.progress(1.0, text="Gotowe")
                st.success(f"Modele 1–7 dni i plan na 2 miesiące zapisane (dostępne dni: {P.dostepne_dni()}).")
        if st.button("Wytrenuj model na wszystkich danych z bazy", key="model_trenuj"):
            d = st.session_state.get("d_baza")
            if d is None:
                st.error("Brak danych z bazy.")
            else:
                with st.spinner("Trening..."):
                    P.trenuj(d)
                st.rerun()
