"""
Wyglad aplikacji - kolory, wspolny styl wykresow plotly i CSS dla streamlita.

tu wpisywac kolory
"""

import streamlit as st

# paleta: blekity (woda) + szarosci; czerwien zarezerwowana dla anomalii
COL_PRIMARY = "#2272AE"      # naglowki, glowna seria, przyciski
COL_PRIMARY_DARK = "#1A5C90"  # hover, wartosci kafelkow
COL_ACCENT = "#58B2E3"       # druga seria, linie bazowe
COL_ANOM = "#C00000"
COL_GRID = "#E1EBF4"
COL_TEXT = "#1B2A38"
COL_BORDER = "#C7DDF0"       # ramki kart, tabel, zakladek
COL_SURFACE = "#EEF5FB"      # tlo panelu bocznego
COL_AXIS = "#8FA9C0"

"""opis z-score uzywany w kilku miejscach (zakladka Anomalie, Detekcja) - zeby byl
 wszedzie taki sam tekst, trzymamy go w jednym miejscu zamiast kopiowac po plikach """
ZSCORE_HELP = (
    "Z-score mowi o ile odchylen standardowych dana wartosc odstaje od sredniej calej kolumny. "
    "0 = dokladnie srednia, 1 = jedno odchylenie powyzej, -2 = dwa odchylenia ponizej. "
    "Umownie |z| > 3 uznaje sie za wartosc nietypowa. "
    "Uwaga: srednia i odchylenie sa liczone z calej kolumny, wiec pojedyncza skrajna wartosc "
    "potrafi zawyzyc odchylenie i zaniżyc z-score pozostalych wierszy."
)

""" wspolny wyglad wszystkich wykresow - bialy, kanciasty, chlodne linie siatki
zostaw uzywane przez kazdy wykres w wykresy.py by sie nikt nie przywalal"""
PLOT_LAYOUT = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(color=COL_TEXT, size=12),
    title_font=dict(color=COL_PRIMARY_DARK, size=14),
    margin=dict(l=50, r=20, t=80, b=45),
    hoverlabel=dict(bgcolor="white", bordercolor=COL_PRIMARY, font_size=12),
    # legenda poziomo nad wykresem - dlugie nazwy nie zjadaja szerokosci
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=11)),
    colorway=[COL_PRIMARY, COL_ACCENT, COL_ANOM, "#E8A33D", "#6B8CA8"],
)

# dla plotly konfiguracja tez nie zmieniac, wyglada ok dla osi to jest
AXIS_STYLE = dict(showgrid=True, gridcolor=COL_GRID, gridwidth=1,
                  linecolor=COL_AXIS, linewidth=1, mirror=True, ticks="outside")


class Wyglad:
    """Caly CSS aplikacji w jednym miejscu. Wywolywane raz, na samej gorze app.py,
    zanim cokolwiek innego sie wyrysuje."""

    @staticmethod
    def zastosuj():
        """motyw: jasne blekity, kanciaste elementy, subtelny gradient tla"""

        st.markdown(
            f"""
            <style>
            /* Deploy i reszta opcji deweloperskich sa juz ukryte przez
            [client] toolbarMode = "viewer" w .streamlit/config.toml */

            /* zwijanie sidebara psulo sie (strzalka do przywrocenia znikala
            razem z paskiem Deploy) - prosciej jest w ogole zablokowac
            mozliwosc zwiniecia, sidebar zostaje zawsze widoczny.
            Bez ograniczenia do konkretnego tagu, bo w skompilowanym froncie
            ten sam data-testid moze byc na wrapperze, nie na <button> */
            [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
            [data-testid="stSidebarCollapseButton"] * {{ display: none !important; }}

            /* wszystko kanciaste - zero zaokraglen */
            .stApp *, .stApp *::before, .stApp *::after {{ border-radius: 0 !important; }}

            /* subtelny blekitny gradient tla, przechodzacy w biel */
            .stApp {{
                background: linear-gradient(180deg, #E6F1FA 0%, #F5FAFE 260px, #FFFFFF 560px) no-repeat;
                background-color: #FFFFFF;
            }}
            header[data-testid="stHeader"] {{ background: transparent; }}

            section[data-testid="stSidebar"] {{
                background-color: {COL_SURFACE};
                border-right: 1px solid {COL_BORDER};
            }}

            h1, h2, h3, h4 {{ color: {COL_PRIMARY_DARK}; font-weight: 700; }}
            h1 {{
                font-size: 2rem; letter-spacing: 0.2px; padding-bottom: 6px;
                border-bottom: 3px solid; border-image: linear-gradient(90deg, {COL_PRIMARY}, {COL_ACCENT} 55%, rgba(88,178,227,0)) 1;
            }}

            /* zakladki (Streamlit >= 1.5x: react-aria, atrybuty data-testid / data-selected / data-hovered, bez data-baseweb).
            Glowny poziom: plaskie, podkreslenie aktywnej; selektory z .stApp dla pewnego priorytetu nad stylami Streamlita */
            .stApp .stTabs [role="tablist"] {{ gap: 4px; }}
            .stApp .stTabs [role="tablist"]::after {{ height: 2px; background-color: {COL_BORDER}; }}
            .stApp .stTabs [data-testid="stTab"] {{ padding: 0 18px; font-weight: 600; color: #3E566B; }}
            .stApp .stTabs [data-testid="stTab"][data-hovered] {{ background-color: rgba(34,114,174,0.08); color: {COL_PRIMARY_DARK}; }}
            .stApp .stTabs [data-testid="stTab"][data-selected] {{ color: {COL_PRIMARY_DARK}; }}
            .stApp .stTabs [data-testid="stTab"] .react-aria-SelectionIndicator {{ height: 3px; }}
            .stApp .stTabs [data-testid="stTab"][data-selected] .react-aria-SelectionIndicator {{ background-color: {COL_PRIMARY}; }}

            /* ostatnia zakladka glownego poziomu (Zalecenia dla uzytkownika): wypelnione tlo, przy prawej krawedzi.
            Regula obejmuje ostatnia zakladke kazdego paska i jest cofana nizej dla podzakladek (dwukrotne .stTabs) */
            .stApp .stTabs [role="tablist"] > [data-testid="stTab"]:last-child {{
                margin-left: auto; background-color: #DCEBF8; border: 1px solid #AFCBE6; color: {COL_PRIMARY_DARK};
            }}
            .stApp .stTabs [role="tablist"] > [data-testid="stTab"]:last-child[data-hovered] {{ background-color: #CBE1F4; }}
            .stApp .stTabs [role="tablist"] > [data-testid="stTab"]:last-child[data-selected] {{
                background-color: {COL_PRIMARY}; border-color: {COL_PRIMARY_DARK}; color: #FFFFFF;
            }}
            .stApp .stTabs [role="tablist"] > [data-testid="stTab"]:last-child[data-selected] .react-aria-SelectionIndicator {{
                background-color: {COL_PRIMARY_DARK};
            }}

            /* podzakladki (drugi poziom): mniejsze, lzejsze; cofniecie wyroznienia ostatniej zakladki */
            .stApp .stTabs .stTabs [role="tablist"]::after {{ height: 1px; }}
            .stApp .stTabs .stTabs [data-testid="stTab"] {{ padding: 0 14px; font-weight: 500; font-size: 0.92rem; }}
            .stApp .stTabs .stTabs [data-testid="stTab"][data-selected] .react-aria-SelectionIndicator {{
                height: 2px; background-color: {COL_ACCENT};
            }}
            .stApp .stTabs .stTabs [role="tablist"] > [data-testid="stTab"]:last-child {{
                margin-left: 0; background-color: transparent; border: none; color: #3E566B;
            }}
            .stApp .stTabs .stTabs [role="tablist"] > [data-testid="stTab"]:last-child[data-hovered] {{
                background-color: rgba(34,114,174,0.08); color: {COL_PRIMARY_DARK};
            }}
            .stApp .stTabs .stTabs [role="tablist"] > [data-testid="stTab"]:last-child[data-selected] {{
                background-color: transparent; border: none; color: {COL_PRIMARY_DARK};
            }}
            .stApp .stTabs .stTabs [role="tablist"] > [data-testid="stTab"]:last-child[data-selected] .react-aria-SelectionIndicator {{
                background-color: {COL_ACCENT};
            }}

            /* przyciski */
            .stButton button, .stDownloadButton button {{
                border: 1px solid {COL_PRIMARY}; color: {COL_PRIMARY_DARK}; font-weight: 600;
            }}
            .stButton button:hover, .stDownloadButton button:hover {{ background-color: rgba(34,114,174,0.08); }}
            .stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {{
                background-color: {COL_PRIMARY}; border: 1px solid {COL_PRIMARY_DARK}; color: #FFFFFF;
            }}
            .stButton button[kind="primary"]:hover, .stDownloadButton button[kind="primary"]:hover {{
                background-color: {COL_PRIMARY_DARK};
            }}

            /* pola tekstowe i liczbowe */
            .stNumberInput input, .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {{
                border: 1px solid #9DB6CC;
            }}

            /* kafelki metryk: biala karta z akcentem po lewej */
            div[data-testid="stMetric"] {{
                background-color: rgba(255,255,255,0.85);
                border: 1px solid {COL_BORDER};
                border-left: 4px solid {COL_PRIMARY};
                padding: 10px 12px;
            }}
            div[data-testid="stMetricValue"] {{
                color: {COL_PRIMARY_DARK};
                font-variant-numeric: tabular-nums;
            }}

            /* tabele i rozwijane sekcje */
            div[data-testid="stDataFrame"] {{ border: 1px solid {COL_BORDER}; }}
            div[data-testid="stExpander"] {{ border: 1px solid {COL_BORDER}; background-color: rgba(255,255,255,0.7); }}
            </style>
            """,
            unsafe_allow_html=True,
        )
