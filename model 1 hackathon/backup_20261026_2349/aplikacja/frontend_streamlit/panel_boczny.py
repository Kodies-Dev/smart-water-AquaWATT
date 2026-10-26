"""
Panel boczny - wgrywanie plikow, wybor zbioru aktywnego, limit punktow
na wykresach. To pierwsza rzecz jaka uzytkownik widzi, wiec ma byc
prosto i bez niespodzianek.
"""

import pandas as pd
import streamlit as st

from frontend_streamlit.magazyn_danych import MagazynDanych


def renderuj():
    """Caly panel boczny. Wywolac raz, przed zakladkami."""

    # to z lewej niestety za bardzo nie da sie ustawiac inaczej, chyba ze przez CSS minus streamlita
    st.sidebar.title("Prognoza energii")

    # --- dane z bazy po ETL (projekt hackathonu) - zrodlo dla naszego potoku anomalii
    st.sidebar.markdown("**Dane z bazy (po ETL)**")
    if st.sidebar.button("Wczytaj z bazy", width="stretch",
                         help="Tabele godzinowe ze wszystkich pompowni (energia, przeplyw, SCADA, opad, pogoda, "
                              "kalendarz) - historia i pogoda dla prognozy. Wymaga dzialajacej bazy - python main.py etl."):
        try:
            from backend_ml_llm.nasz_detektor import nasz_detektor
            with st.sidebar.status("Wczytuje tabele z bazy..."):
                d, alarmy = nasz_detektor.dane_z_bazy()
            st.session_state.d_baza, st.session_state.alarmy = d, alarmy
            nazwa = MagazynDanych.dodaj("baza_dobowo", nasz_detektor.dobowo_do_podgladu(d))
            st.sidebar.success(f"{nazwa}: {d['energia']['obiekt_id'].nunique()} pompowni, "
                               f"{len(d['energia']):,} godzin energii")
        except Exception as e:
            st.sidebar.error(f"Nie udalo sie wczytac bazy: {e}")
    st.sidebar.divider()

    uploaded = st.sidebar.file_uploader(
        "Wgraj pliki CSV lub Excel", type=["csv", "xlsx", "xls"], accept_multiple_files=True,
        help="Mozna wgrac kilka plikow naraz i porownywac je miedzy soba w zakladce Dane.",
    )

    if uploaded:  # jezeli cokolwiek wgrane
        ma_excel = any(u.name.lower().endswith((".xlsx", ".xls")) for u in uploaded)  # czy conajmniej jeden excel

        if ma_excel:
            # Z pliku Excel bierzemy TYLKO PIERWSZY arkusz. Kolejne sa ignorowane -
            # zwykle sa to zestawienia pomocnicze o innej strukturze, ktorych nie da sie
            # analizowac razem z pierwszym.
            wiersz_naglowka = st.sidebar.number_input(
                "Wiersz z naglowkami (Excel)", min_value=1, value=1, step=1,
                help="Numer wiersza z nazwami kolumn. Ustaw wiecej niz 1, jesli arkusz "
                     "zaczyna sie tytulem lub pustymi wierszami.",
            )
        else:
            wiersz_naglowka = 1

        ma_csv = any(u.name.lower().endswith(".csv") for u in uploaded)  # czy sa jakiekolwiek pliki csv
        if ma_csv:
            sep = st.sidebar.selectbox("Separator (CSV)", [",", ";", "\t", "|"], index=0)
            kodowanie = st.sidebar.text_input("Kodowanie (CSV)", value="utf-8")
        else:
            sep = ","
            kodowanie = "utf-8"

        if st.sidebar.button("Wczytaj pliki", type="primary", width="stretch"):
            for u in uploaded:
                try:
                    if u.name.lower().endswith((".xlsx", ".xls")):
                        arkusze = pd.ExcelFile(u).sheet_names
                        df_new = pd.read_excel(u, sheet_name=0, header=int(wiersz_naglowka) - 1)
                        if len(arkusze) > 1:
                            st.sidebar.info(f"{u.name}: wczytano tylko pierwszy arkusz "
                                            f"('{arkusze[0]}' z {len(arkusze)}).")
                    else:
                        df_new = pd.read_csv(u, sep=sep, encoding=kodowanie)

                    df_new = MagazynDanych.sprzataj_kolumny(df_new)
                    nazwa = MagazynDanych.dodaj(u.name.rsplit(".", 1)[0], df_new)
                    st.sidebar.success(f"{nazwa}: {len(df_new)} wierszy")
                except Exception as e:
                    st.sidebar.error(f"{u.name} - blad wczytywania: {e}")

    if st.session_state.zbiory:
        st.sidebar.divider()  # zwykla linia
        st.session_state.aktywny = st.sidebar.selectbox(
            "Zbior aktywny", list(st.session_state.zbiory.keys()),
            index=list(st.session_state.zbiory.keys()).index(st.session_state.aktywny)
            if st.session_state.aktywny in st.session_state.zbiory else 0,
            help="Ten zbior trafia do wykresow, detekcji i raportu.",
        )
        akt = st.session_state.zbiory[st.session_state.aktywny]
        st.sidebar.caption(  # wyblakly tekst
            f"Wierszy: {len(akt)} | Kolumn: {len(akt.columns)} | "
            f"Zbiorow w pamieci: {len(st.session_state.zbiory)}"
        )

        st.sidebar.divider()
        st.session_state.limit_punktow = st.sidebar.number_input(
            "Maks. punktow na wykresie", min_value=0, value=st.session_state.limit_punktow, step=1000,
            help="0 oznacza brak ograniczen - rysowane sa wszystkie punkty. Przy bardzo duzych "
                 "zbiorach ustawienie limitu przyspiesza rysowanie kosztem szczegolowosci.",
        )
