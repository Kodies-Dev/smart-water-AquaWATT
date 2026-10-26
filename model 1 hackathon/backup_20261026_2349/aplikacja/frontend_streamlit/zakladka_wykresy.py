"""
Zakladka Wykresy - eksploracja surowych danych przed detekcja anomalii.
Wykres liniowy, histogram, boxplot, korelacje.
"""

import streamlit as st

from frontend_streamlit.magazyn_danych import MagazynDanych
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.pola import Pola
from frontend_streamlit.wykresy import Wykresy


def renderuj():
    raw_df = MagazynDanych.aktywny_df()
    all_num_cols = list(raw_df.select_dtypes(include="number").columns)

    st.subheader("Eksploracja danych")

    if not all_num_cols:
        # zbior moze byc tekstowy - np. slownik wgrany tylko po to, zeby go z czyms polaczyc
        st.warning(f"Zbior '{st.session_state.aktywny}' nie ma kolumn liczbowych, wiec nie ma czego "
                   "pokazac na wykresach. Wybierz inny zbior w panelu bocznym albo polacz "
                   "go z innym w zakladce Dane.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        row_from = Pola.num_field("Wiersz od", 0, len(raw_df) - 1, 0, 1, "row_from",
                                  help="Ogranicz zakres, zeby przyjrzec sie fragmentowi duzego pliku.")
    with c2:
        row_to = Pola.num_field("Wiersz do", 1, len(raw_df), min(len(raw_df), 1000), 1, "row_to")
    with c3:
        bins = Pola.num_field("Liczba przedzialow (histogram)", 5, 200, 40, 1, "bins")

    if row_to <= row_from:  # zabezpieczenie przed odwroconym zakresem
        st.caption(f"Koniec zakresu musi byc wiekszy od poczatku - uzyto {row_from + 1}.")
        row_to = row_from + 1

    view = raw_df.iloc[row_from:row_to]
    st.caption(f"Widok: wiersze {row_from}-{row_to} ({len(view)} z {len(raw_df)})")

    st.markdown("#### Wykres liniowy")
    line_cols = st.multiselect("Kolumny", all_num_cols, default=all_num_cols[:1], key="line_cols")
    if line_cols:
        lim_line = Pola.axis_fields("line")
        plot_view, step = Narzedzia.downsample(view)
        if step > 1:
            st.caption(f"Bardzo duzo wartosci - wykres pokazuje co {step}. wiersz.")
        Wykresy.show(Wykresy.fig_line(plot_view, line_cols, "Przebieg wartosci", lim_line))
        st.caption("Najedz na punkt, zeby zobaczyc wartosc. Kolko myszy przybliza, przeciaganie przesuwa.")
    else:
        st.info("Wybierz przynajmniej jedna kolumne.")

    st.markdown("#### Histogram")
    hist_col = st.selectbox("Kolumna", all_num_cols, key="hist_col")
    lim_hist = Pola.axis_fields("hist")
    Wykresy.show(Wykresy.fig_hist(view, hist_col, bins, lim_hist))

    st.markdown("#### Boxplot")
    box_cols = st.multiselect("Kolumny", all_num_cols, default=all_num_cols[:4], key="box_cols")
    if box_cols:
        lim_box = Pola.axis_fields("box")
        Wykresy.show(Wykresy.fig_box(view, box_cols, lim_box))

    if len(all_num_cols) > 1:
        st.markdown("#### Korelacje")
        Wykresy.show(Wykresy.fig_corr(view, all_num_cols))
