"""
Wyglad aplikacji - kolory, wspolny styl wykresow plotly i CSS dla streamlita.

tu wpisywac kolory
"""

import streamlit as st

# paleta w stylu Excel/GUS - granat, zielen, szarosci
COL_PRIMARY = "#1F4E79"
COL_ACCENT = "#217346"
COL_ANOM = "#C00000"
COL_GRID = "#D9D9D9"
COL_TEXT = "#333333"

"""opis z-score uzywany w kilku miejscach (zakladka Anomalie, Detekcja) - zeby byl
 wszedzie taki sam tekst, trzymamy go w jednym miejscu zamiast kopiowac po plikach """
ZSCORE_HELP = (
    "Z-score mowi o ile odchylen standardowych dana wartosc odstaje od sredniej calej kolumny. "
    "0 = dokladnie srednia, 1 = jedno odchylenie powyzej, -2 = dwa odchylenia ponizej. "
    "Umownie |z| > 3 uznaje sie za wartosc nietypowa. "
    "Uwaga: srednia i odchylenie sa liczone z calej kolumny, wiec pojedyncza skrajna wartosc "
    "potrafi zawyzyc odchylenie i zaniżyc z-score pozostalych wierszy."
)

""" wspolny wyglad wszystkich wykresow - bialy, kanciasty, jak w arkuszu excel/gus
zostaw uzywane przez kazdy wykres w wykresy.py by sie nikt nie przywalal"""
PLOT_LAYOUT = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(color=COL_TEXT, size=12),
    title_font=dict(color=COL_PRIMARY, size=14),
    margin=dict(l=50, r=20, t=50, b=45),
    hoverlabel=dict(bgcolor="white", bordercolor=COL_PRIMARY, font_size=12), #dymek zayebisty
    legend=dict(bordercolor="#8C8C8C", borderwidth=1),
)

# dla plotly konfiguracja tez nie zmieniac, wyglada ok dla osi to jest
AXIS_STYLE = dict(showgrid=True, gridcolor=COL_GRID, gridwidth=1,
                  linecolor="#8C8C8C", linewidth=1, mirror=True, ticks="outside")


class Wyglad:
    """Caly CSS aplikacji w jednym miejscu. Wywolywane raz, na samej gorze app.py,
    zanim cokolwiek innego sie wyrysuje."""

    @staticmethod
    def zastosuj():
        """motyw excelowo gusowy zostaw"""

        st.markdown(
            """
            <style>
            /* Deploy i reszta opcji deweloperskich sa juz ukryte przez
            [client] toolbarMode = "viewer" w .streamlit/config.toml */

            /* zwijanie sidebara psulo sie (strzalka do przywrocenia znikala
            razem z paskiem Deploy) - prosciej jest w ogole zablokowac
            mozliwosc zwiniecia, sidebar zostaje zawsze widoczny.
            Bez ograniczenia do konkretnego tagu, bo w skompilowanym froncie
            ten sam data-testid moze byc na wrapperze, nie na <button> */
            [data-testid="stSidebarCollapseButton"] { display: none !important; }
            [data-testid="stSidebarCollapseButton"] * { display: none !important; }

            /* wszystko kanciaste - zero zaokraglen */
            .stApp *, .stApp *::before, .stApp *::after { border-radius: 0 !important; }

            section[data-testid="stSidebar"] {
                border-right: 1px solid #BFBFBF;
            }

            h1, h2, h3, h4 { color: #1F4E79; font-weight: 700; }
            h1 { border-bottom: 3px solid #1F4E79; padding-bottom: 6px; }

            /* zakladki jak w arkuszu kalkulacyjnym */
            .stTabs [data-baseweb="tab-list"] {
                gap: 0;
                border-bottom: 1px solid #BFBFBF;
            }
            .stTabs [data-baseweb="tab"] {
                background-color: #F2F2F2;
                border: 1px solid #BFBFBF;
                border-bottom: none;
                margin-right: 2px;
                padding: 6px 16px;
            }
            .stTabs [aria-selected="true"] {
                background-color: #FFFFFF;
                border-top: 3px solid #1F4E79;
                font-weight: 700;
            }

            /* przyciski */
            .stButton button, .stDownloadButton button {
                border: 1px solid #1F4E79;
                font-weight: 600;
            }
            .stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {
                background-color: #1F4E79;
                border: 1px solid #16375A;
            }

            /* pola tekstowe i liczbowe */
            .stNumberInput input, .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
                border: 1px solid #8C8C8C;
            }

            /* metryki jak komorki arkusza */
            div[data-testid="stMetric"] {
                background-color: #F2F2F2;
                border: 1px solid #BFBFBF;
                padding: 10px;
            }
            div[data-testid="stMetricValue"] {
                color: #1F4E79;
                font-variant-numeric: tabular-nums;
            }

            /* tabele */
            div[data-testid="stDataFrame"] { border: 1px solid #BFBFBF; }
            </style>
            """,
            unsafe_allow_html=True,
        )
