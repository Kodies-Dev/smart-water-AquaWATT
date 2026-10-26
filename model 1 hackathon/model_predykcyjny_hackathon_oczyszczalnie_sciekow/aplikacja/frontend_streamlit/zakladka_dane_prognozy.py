"""
Zakladka Dane - dane do prognozy wczytane w panelu bocznym: podsumowanie i wykres w czasie, a pod spodem narzedzia
z Detektora GUS (podglad, statystyki, porownanie, laczenie, tabela przestawna, SQL) na tym samym zbiorze.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frontend_streamlit import zakladka_dane
from frontend_streamlit.magazyn_danych import MagazynDanych
from frontend_streamlit.styles import COL_PRIMARY, COL_ANOM
from frontend_streamlit.wykresy import Wykresy


def _zbior_aktywny():
    """Wybor zbioru aktywnego jak w Detektorze GUS + dokladanie innych plikow (porownanie, laczenie)."""
    nazwy = list(st.session_state.zbiory)
    if st.session_state.get("dp_aktywny") not in nazwy:
        st.session_state.pop("dp_aktywny", None)
    c1, c2 = st.columns([2, 3])
    with c1:
        st.session_state.aktywny = st.selectbox(
            "Zbiór aktywny", nazwy, key="dp_aktywny",
            index=nazwy.index(st.session_state.aktywny) if st.session_state.aktywny in nazwy else 0,
            help="dane_do_prognozy = plik z panelu po lewej, baza_dobowo = wszystkie pompownie dobowo, "
                 "plus pliki dodane obok. Ten zbiór trafia do narzędzi poniżej i do zakładki Wykresy.")
        akt = st.session_state.zbiory[st.session_state.aktywny]
        st.caption(f"Wierszy: {len(akt)} | Kolumn: {len(akt.columns)} | Zbiorów w pamięci: {len(nazwy)}")
    with c2:
        with st.expander("Dodaj inne pliki (CSV / Excel) – do porównania i łączenia"):
            pliki = st.file_uploader("Pliki", type=["csv", "xlsx", "xls"], accept_multiple_files=True, key="dp_inne",
                                     label_visibility="collapsed")
            k1, k2, k3 = st.columns(3)
            sep = k1.selectbox("Separator (CSV)", [";", ",", "\t", "|"], key="dp_sep")
            kod = k2.text_input("Kodowanie (CSV)", value="utf-8", key="dp_kod")
            nagl = k3.number_input("Wiersz nagłówka (Excel)", min_value=1, value=1, step=1, key="dp_nagl")
            if pliki and st.button("Wczytaj pliki", key="dp_wczytaj"):
                for u in pliki:
                    try:
                        if u.name.lower().endswith((".xlsx", ".xls")):
                            df = pd.read_excel(u, sheet_name=0, header=int(nagl) - 1)
                        else:
                            df = pd.read_csv(u, sep=sep, encoding=kod)
                        nazwa = MagazynDanych.dodaj(u.name.rsplit(".", 1)[0], MagazynDanych.sprzataj_kolumny(df))
                        st.session_state.dp_aktywny = nazwa
                        st.success(f"{nazwa}: {len(df)} wierszy")
                    except Exception as e:
                        st.error(f"{u.name} – błąd wczytywania: {e}")
                st.rerun()


def renderuj():
    st.subheader("Dane")
    dp = st.session_state.get("dane_prognozy")
    if dp is None:
        st.info("Wgraj plik(i) z danymi do prognozy w panelu po lewej.")
    if st.session_state.zbiory:
        _zbior_aktywny()
    if dp is not None and st.session_state.aktywny == "dane_do_prognozy":
        d = st.session_state.get("d_baza")
        h = dp["nowe"].set_index("czas")["kwh"]
        lok = h.index.tz_convert("Europe/Warsaw")
        doby = h.groupby(lok.date).agg(["sum", "count"])
        doby = doby[doby["count"] >= 23]["sum"]
        st.markdown(f"### Dane do prognozy – {dp['oid']}")
        braki = int(pd.date_range(h.index.min(), h.index.max(), freq="h").difference(h.index).size)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Okres", f"{lok.min():%d.%m} – {lok.max():%d.%m.%Y}")
        c2.metric("Pełnych dób", f"{len(doby)}")
        c3.metric("Zużycie razem", f"{h.sum():,.0f} kWh".replace(",", " "))
        c4.metric("Średnio na dobę", f"{doby.mean():,.0f} kWh".replace(",", " "))
        st.caption(f"Źródło: {dp['zrodlo']} · format: {dp['rodzaj']} · zużycie dobowe od {doby.min():.0f} do {doby.max():.0f} kWh · "
                   + ("dane kompletne" if braki == 0 else f"brakujących godzin: {braki} (model sobie z tym poradzi)"))
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
