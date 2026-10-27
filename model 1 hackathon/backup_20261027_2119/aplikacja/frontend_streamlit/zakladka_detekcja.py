"""
Zakladka Detekcja - zrodlo danych (baza po ETL albo wgrany CSV godzinowy), parametry i uruchomienie
naszego potoku anomalii (zespol IF + LOF + One-Class SVM per pompownia, >= 2 z 3).
Wynik ma kolumny jak w anomaly_d.py, wiec zakladki Raport i Pytanie dzialaja bez zmian.
"""

import streamlit as st

from backend_ml_llm.nasz_detektor import nasz_detektor, KOLUMNY_GODZINOWE
from frontend_streamlit.magazyn_danych import MagazynDanych
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.pola import Pola


def _zrodlo():
    """Zwraca (slownik tabel, alarmy albo None) wedlug wybranego zrodla."""
    zrodlo = st.radio(
        "Zrodlo danych",
        ["Baza (po ETL) - wszystkie pompownie", "Aktywny zbior - CSV godzinowy"],
        key="zrodlo_anomalii",
        help="Baza: pelne dane z ETL (energia, przeplyw, SCADA, opad, pogoda, kalendarz) i alarmy tloczni CH "
             "do doboru odsetka. CSV godzinowy: kolumny czas, kwh oraz opcjonalnie obiekt_id, m3, opad_mm, temp_c.",
    )
    if zrodlo.startswith("Baza"):
        if st.session_state.get("d_baza") is None:
            st.info("Kliknij 'Wczytaj z bazy' w panelu bocznym.")
            return None, None
        return st.session_state.d_baza, st.session_state.get("alarmy")
    df = MagazynDanych.aktywny_df()
    brak = [c for c in ["czas", "kwh"] if c not in df.columns]
    if brak:
        st.warning(f"Aktywny zbior '{st.session_state.aktywny}' nie ma kolumn {brak}. "
                   f"Format: {', '.join(KOLUMNY_GODZINOWE)} (wymagane: czas, kwh).")
        return None, None
    return nasz_detektor.dane_z_godzinowego(df), None


def renderuj():
    st.subheader("Detekcja anomalii w sieci kanalizacyjnej")

    with st.expander("Jak to dziala"):
        st.markdown("""
1. Dla kazdej pompowni i doby liczymy cechy: **nadwyzke przeplywu ponad baze bezdeszczowa**, udzial przeplywu
   nocnego (infiltracja), **energie ponad prognoze modelu** (XGBoost out-of-fold, z pogoda zmierzona),
   kWh/m³ (sprawnosc pomp), prace pomp, opad, temperature, roztopy.
2. Tryb panelowy jak w Detektorze GUS: **nagla zmiana** wzgledem wlasnych dob i **odstawanie od innych
   pompowni tego samego dnia** (ta sama pogoda).
3. Isolation Forest, LOF i One-Class SVM glosuja osobno dla kazdej pompowni - **anomalia = co najmniej 2 z 3**.
4. Reguly nadaja **typ**: doplyw opadowy, roztopy, infiltracja / doplyw bez deszczu, spadek (awaria),
   spadek sprawnosci pomp. Glowna przyczyna = cecha skutku z najwyzszym |z-score|.
""")

    d, alarmy = _zrodlo()
    if d is None:
        return

    st.markdown("#### Parametry")
    c1, c2, c3 = st.columns(3)
    with c1:
        okno = Pola.num_field("Okno kroczace [doby]", 3, 60, 14, 1, "okno_panel",
                              help="Ile poprzednich dob danej pompowni wchodzi do sredniej przy liczeniu naglej zmiany.")
    with c2:
        auto = st.checkbox("Dobierz odsetek na alarmach CH", value=alarmy is not None and len(alarmy) > 0,
                           disabled=alarmy is None or len(alarmy) == 0,
                           help="Sprawdza 2 / 3 / 5 / 8% i wybiera najlepszy kompromis: ile dni z alarmem tloczni "
                                "zespol zlapal (±1 doba) i ile jego wskazan wypadlo przy alarmach.")
    with c3:
        odsetek = Pola.num_field("Oczekiwany odsetek anomalii", 0.005, 0.3, 0.05, 0.01, "odsetek_anomalii",
                                 is_int=False, help="Uzywany, gdy nie dobieramy go na alarmach. Kazdy model wskazuje "
                                                    "mniej wiecej tyle procent dob danej pompowni.")

    if st.button("Uruchom detekcje", type="primary"):
        with st.spinner("Licze cechy dobowe i prognoze energii (out-of-fold), uruchamiam modele..."):
            try:
                dz = nasz_detektor.cechy(d, okno=okno)
                walid, powod = None, "ustawiony recznie"
                if auto:
                    odsetek, walid, powod = nasz_detektor.dobierz_odsetek(dz, alarmy)
                res, num_cols, uzyte = nasz_detektor.detect(dz, odsetek)
                st.session_state.result_df, st.session_state.num_cols = res, num_cols
                st.session_state.report = None
                st.session_state.anom_extra = dict(odsetek=odsetek, powod=powod, walidacja=walid, uzyte=uzyte,
                                                   nazwy=nasz_detektor.NAZWY_CECH, **nasz_detektor.podsumowania(res))
                st.session_state.group_col, st.session_state.time_col = "obiekt_id", "dzien"
            except Exception as e:
                st.error(f"Blad detekcji: {e}")

    if st.session_state.result_df is None or "Anomaly_Final" not in st.session_state.result_df:
        return

    res = st.session_state.result_df
    ex = st.session_state.get("anom_extra", {})
    ocenione = int(res["glosy"].notna().sum())
    st.success(f"Gotowe. Wykryto {int(res['Anomaly_Final'].sum())} anomalii na {ocenione} ocenionych dob "
               f"(odsetek {ex.get('odsetek', 0):.0%} - {ex.get('powod', '')}).")

    glosy = {"Isolation Forest": int(res["Anomaly_IF"].sum()),
             "LOF": int(res["Anomaly_LOF"].sum()),
             "One-Class SVM": int(res["Anomaly_SVM"].sum())}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Isolation Forest", glosy["Isolation Forest"])
    c2.metric("LOF", glosy["LOF"])
    c3.metric("One-Class SVM", glosy["One-Class SVM"])
    c4.metric("Finalnie (>=2/3)", int(res["Anomaly_Final"].sum()))

    puste = [n for n, v in glosy.items() if v == 0]
    if puste:
        st.warning(f"Model {' i '.join(puste)} nie wskazal zadnej doby, wiec nie bierze udzialu w glosowaniu - "
                   f"wynik opiera sie na pozostalych. Rozwaz podniesienie oczekiwanego odsetka anomalii.")

    walid = ex.get("walidacja")
    if walid is not None and len(walid):
        st.markdown("#### Walidacja na alarmach tloczni CH (±1 doba)")
        st.caption("`zlapane_*` - ile dni z alarmem wskazano, `trafienia_przy_alarmie` - ile wskazan wypadlo przy "
                   "alarmie, `lift` - ile razy lepiej niz losowy wybor dni.")
        st.dataframe(walid.round(1), width="stretch")

    a = res[res["Anomaly_Final"] == 1]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Typ anomalii")
        st.dataframe(a.groupby(["obiekt_id", "typ"]).size().unstack(fill_value=0), width="stretch")
    with c2:
        st.markdown("#### Rodzaj (tryb panelowy)")
        st.dataframe(a.groupby(["obiekt_id", "Rodzaj_Anomalii"]).size().unstack(fill_value=0), width="stretch")

    st.markdown("#### Wykryte anomalie")
    kol = ["obiekt_id", "dzien", "typ", "Rodzaj_Anomalii", "glowna_cecha", "z_glownej", "Anomaly_IF", "Anomaly_LOF",
           "Anomaly_SVM", "Anomaly_Votes", "Has_Outlier", "skala_m3", "skala_kwh", "opad_3d", "opis"]
    st.dataframe(a[[c for c in kol if c in a.columns]], width="stretch")

    with st.expander("Cechy uzyte per pompownia"):
        for oid, cols in ex.get("uzyte", {}).items():
            st.markdown(f"**{oid}**: {', '.join(cols)}")

    Narzedzia.przycisk_pobierania(
        "Pobierz pelny wynik (CSV)", Narzedzia.to_csv_bytes(res), "wynik_anomalie.csv", "text/csv", key="pob_pelny")
    Narzedzia.przycisk_pobierania(
        "Pobierz same anomalie (CSV)", Narzedzia.to_csv_bytes(a), "anomalie.csv", "text/csv", key="pob_anom")
