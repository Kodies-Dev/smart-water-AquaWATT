"""
Zakladka Dane - dane do prognozy wczytane w panelu bocznym: podsumowanie i wykres w czasie, a pod spodem narzedzia
z Detektora GUS (podglad, statystyki, porownanie, laczenie, tabela przestawna, SQL) na tym samym zbiorze.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frontend_streamlit import zakladka_dane
from frontend_streamlit.styles import COL_PRIMARY, COL_ANOM
from frontend_streamlit.wykresy import Wykresy


def renderuj():
    dp = st.session_state.get("dane_prognozy")
    if dp is None:
        st.subheader("Dane do prognozy")
        st.info("Wgraj plik z danymi albo wybierz pompownię z bazy w panelu po lewej.")
    else:
        d = st.session_state.get("d_baza")
        if dp["nowe"] is not None:
            h = dp["nowe"].set_index("czas")["kwh"]
        else:
            e = d["energia"][d["energia"]["obiekt_id"] == dp["oid"]]
            h = e[e["czas"] > e["czas"].max() - pd.Timedelta(weeks=8)].set_index("czas")["kwh"]
        lok = h.index.tz_convert("Europe/Warsaw")
        doby = h.groupby(lok.date).agg(["sum", "count"])
        doby = doby[doby["count"] >= 23]["sum"]
        st.subheader(f"Dane do prognozy – {dp['oid']}")
        st.caption(f"Źródło: {dp['zrodlo']}" + (f" · format: {dp['rodzaj']}" if dp["rodzaj"] != "baza" else " · ostatnie 8 tygodni"))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Okres", f"{lok.min():%d.%m} – {lok.max():%d.%m.%Y}", f"{len(doby)} pełnych dób", delta_color="off")
        c2.metric("Zużycie razem", f"{h.sum():,.0f} kWh".replace(",", " "))
        c3.metric("Średnio na dobę", f"{doby.mean():,.0f} kWh".replace(",", " "),
                  f"od {doby.min():.0f} do {doby.max():.0f}", delta_color="off")
        braki = int(pd.date_range(h.index.min(), h.index.max(), freq="h").difference(h.index).size)
        c4.metric("Brakujące godziny", f"{braki}", "kompletne dane" if braki == 0 else "model sobie z tym poradzi",
                  delta_color="off")
        if len(h) < 24 * 35 and dp["oid"] not in (d["energia"]["obiekt_id"].unique() if d is not None else []):
            st.warning("Mniej niż 5 tygodni danych dla pompowni spoza bazy – prognoza nie będzie możliwa.")

        widok = st.radio("Widok", ["dobowo", "godzinowo"], horizontal=True, key="dp_widok")
        fig = go.Figure()
        if widok == "dobowo":
            fig.add_trace(go.Bar(x=list(doby.index), y=doby.values, marker_color=COL_PRIMARY,
                                 hovertemplate="%{x}<br>%{y:.0f} kWh<extra></extra>", name="kWh / doba"))
            szczyt = doby.idxmax()
            fig.add_trace(go.Bar(x=[szczyt], y=[doby.max()], marker_color=COL_ANOM, name="najwięcej",
                                 hovertemplate="%{x}<br>%{y:.0f} kWh (najwięcej)<extra></extra>"))
            fig.update_layout(barmode="overlay", showlegend=False)
            tytul, y = "Zużycie energii dzień po dniu (czerwony = najwięcej)", "kWh / doba"
        else:
            fig.add_trace(go.Scatter(x=lok, y=h.values, mode="lines", line=dict(color=COL_PRIMARY, width=1.2),
                                     hovertemplate="%{x|%d.%m %H:%M}<br>%{y:.1f} kWh<extra></extra>"))
            tytul, y = "Zużycie energii godzina po godzinie", "kWh / godzinę"
        Wykresy.show(Wykresy.style_fig(go.Figure(fig), tytul, None, y, height=380), key="dp_wykres")
        st.caption("Szczyty to zwykle dni z ulewą – woda deszczowa trafia do kanalizacji i pompy pracują dłużej.")
        st.divider()
        st.markdown("#### Narzędzia do danych")
        st.caption("Podgląd, statystyki, porównanie i łączenie zbiorów, tabela przestawna, SQL – na zbiorze wybranym w panelu "
                   "(domyślnie dane do prognozy).")
    zakladka_dane.renderuj()
