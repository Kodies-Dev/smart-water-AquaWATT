"""
Zakladka Prognoza - szczegoly: na podstawie czego powstala ostatnia prognoza (historia zuzycia, pogoda zmierzona,
prognoza pogody wydana dzien wczesniej, kalendarz), wykresy tych danych, porownanie z prostymi metodami,
na co zwraca uwage model, dane wejsciowe do pobrania. Dane wejsciowe = dokladnie to, co dostal model.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from backend_ml_llm.raport_prognozy import wczytaj_wyniki, nazwa
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.styles import COL_PRIMARY, COL_ACCENT, COL_ANOM
from frontend_streamlit.wykresy import Wykresy

TZ = "Europe/Warsaw"


def tys(n):
    """1234567 -> '1 234 567' (polski separator tysięcy, tylko w liczbach)."""
    return f"{int(n):,}".replace(",", " ")
MIASTA = {"RY": "Rybnik", "RU": "Ruda Śląska", "CH": "Chorzów"}


def _seria(df, kol, idx):
    if df is None or df.empty or kol not in df:
        return pd.Series(float("nan"), index=idx)
    return df.drop_duplicates("czas").set_index("czas")[kol].reindex(idx)


def dane_wejsciowe(wynik, wej):
    """Godzinowo: rzeczywiste, prognoza, opad zmierzony, prognoza opadu (wydana dzien wczesniej), temperatura, dzien wolny."""
    dd = wej["dd"]
    idx = pd.DatetimeIndex(wynik["czas"])
    t = pd.DataFrame({"czas_lokalny": wynik["czas_lokalny"].values, "rzeczywiste_kwh": wynik["rzeczywiste"].values,
                      "prognoza_kwh": wynik["prognoza"].values}, index=idx)
    t["opad_mm"] = _seria(dd["pogoda"], "opad_mm", idx).values
    t["prognoza_opadu_mm"] = _seria(dd["prognoza"], "opad_mm", idx).values
    t["temperatura_c"] = _seria(dd["pogoda"], "temp_c", idx).fillna(_seria(dd["prognoza"], "temp_c", idx)).values
    kal = dd["kalendarz"].copy()
    kal["data"] = pd.to_datetime(kal["data"]).dt.date
    kal = kal.set_index("data")
    dni = t["czas_lokalny"].dt.date
    t["dzien_wolny"] = dni.map(kal["dzien_wolny"]).fillna(False).astype(bool).values
    t["swieto"] = dni.map(kal["nazwa_swieta"]).values if "nazwa_swieta" in kal else None
    t["jutro"] = t.index.isin(wej["przyszlosc"])
    return t


def fig_zuzycie_pogoda(t, dobowo=True):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.55, 0.25, 0.2], vertical_spacing=0.05,
                        subplot_titles=("Zużycie energii", "Deszcz", "Temperatura"))
    if dobowo:
        g = t.groupby(t["czas_lokalny"].dt.date)
        x = list(g.groups)
        rz = g["rzeczywiste_kwh"].sum(min_count=20)
        pr, op, pop, tm = g["prognoza_kwh"].sum(), g["opad_mm"].sum(min_count=1), g["prognoza_opadu_mm"].sum(min_count=1), g["temperatura_c"].mean()
        jedn = "kWh / doba"
    else:
        x, rz, pr = t["czas_lokalny"], t["rzeczywiste_kwh"], t["prognoza_kwh"]
        op, pop, tm, jedn = t["opad_mm"], t["prognoza_opadu_mm"], t["temperatura_c"], "kWh / h"
    fig.add_trace(go.Scatter(x=x, y=rz, name="zużycie rzeczywiste", mode="lines", line=dict(color="#1A1A1A", width=1.6)), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=pr, name="prognoza (z dnia wcześniej)", mode="lines", line=dict(color=COL_ANOM, width=1.3)), 1, 1)
    fig.add_trace(go.Bar(x=x, y=op, name="deszcz zmierzony [mm]", marker_color=COL_PRIMARY, opacity=0.8), 2, 1)
    fig.add_trace(go.Scatter(x=x, y=pop, name="prognoza deszczu sprzed doby [mm]", mode="markers",
                             marker=dict(color=COL_ACCENT, size=5, symbol="diamond")), 2, 1)
    fig.add_trace(go.Scatter(x=x, y=tm, name="temperatura [°C]", mode="lines", line=dict(color="#EF9F27", width=1.3)), 3, 1)
    fig = Wykresy.style_fig(fig, "Zużycie energii na tle pogody (deszcz zwiększa ilość ścieków i pracę pomp)", None, None, height=620)
    fig.update_yaxes(title_text=jedn, row=1, col=1)
    fig.update_yaxes(title_text="mm", row=2, col=1)
    fig.update_yaxes(title_text="°C", row=3, col=1)
    return fig


def fig_jutro_pogoda(t):
    j = t[t["jutro"]]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=j["czas_lokalny"].dt.strftime("%H:%M"), y=j["prognoza_kwh"], name="prognoza zużycia [kWh]",
                         marker_color=COL_PRIMARY), secondary_y=False)
    fig.add_trace(go.Scatter(x=j["czas_lokalny"].dt.strftime("%H:%M"), y=j["prognoza_opadu_mm"], name="prognoza deszczu [mm]",
                             mode="lines+markers", line=dict(color=COL_ACCENT, width=2)), secondary_y=True)
    fig.add_trace(go.Scatter(x=j["czas_lokalny"].dt.strftime("%H:%M"), y=j["temperatura_c"], name="temperatura [°C]",
                             mode="lines", line=dict(color="#EF9F27", width=1.4, dash="dot")), secondary_y=True)
    fig = Wykresy.style_fig(fig, f"Kolejne 24 h: prognoza zużycia i pogody ({j['czas_lokalny'].min():%d.%m.%Y})", "godzina",
                            "kWh w godzinie", height=420)
    fig.update_yaxes(title_text="mm / °C", secondary_y=True, showgrid=False)
    return fig


def renderuj():
    st.subheader("Prognoza – szczegóły")
    prog, wej = st.session_state.get("prog_wynik"), st.session_state.get("prog_dd")
    if prog is None or wej is None:
        st.info("Najpierw przygotuj prognozę w zakładce 'Prognoza' - tutaj zobaczysz, na podstawie czego powstała.")
        return
    oid, wynik, met, mies, jutro = prog
    t = dane_wejsciowe(wynik, wej)
    dd, meta = wej["dd"], wej["meta"]
    stacja = dd["obiekty"]["stacja_pogody"].iloc[0]
    hist = t["rzeczywiste_kwh"].notna().sum()
    dni_wolne = sorted(set(t.loc[t["dzien_wolny"], "czas_lokalny"].dt.date))
    swieta = sorted({(d_, s) for d_, s in zip(t["czas_lokalny"].dt.date, t["swieto"]) if isinstance(s, str) and s})

    st.markdown("#### Na podstawie czego powstała prognoza")
    st.markdown(f"""
- **Historia zużycia energii:** {tys(hist)} godzin ({t['czas_lokalny'].min():%d.%m.%Y} – {t.loc[t['rzeczywiste_kwh'].notna(), 'czas_lokalny'].max():%d.%m.%Y})
  {f"– w tym {tys(wej['z_pliku'])} godzin z pliku, reszta dobrana z bazy" if wej['z_pliku'] else "– z bazy danych"}.
  Model patrzy m.in. na zużycie dobę i tydzień wcześniej, średnie z doby i tygodnia oraz typowy profil z 4 tygodni.
- **Pogoda:** punkt {MIASTA.get(stacja, stacja)} – opad, temperatura, śnieg i wilgotność gleby z ostatnich dni
  (Open-Meteo, dane historyczne ERA5; ostatnie dni i jutro z bieżącej prognozy).
- **Prognoza pogody wydana dzień wcześniej** – deszcz i temperatura na godzinę, dla której liczymy prognozę
  (tak, jak byłoby naprawdę: nie znamy przyszłej pogody, tylko jej prognozę).
- **Kalendarz:** {len(dni_wolne)} dni wolnych w okresie{(" – w tym święta: " + ", ".join(f"{s} ({d_:%d.%m})" for d_, s in swieta[:6])) if swieta else ""}.
- **Model:** {nazwa(meta['wariant'])}, {meta['drzew']} drzew{" – uczony **bez okresu z pliku** (uczciwe sprawdzenie)" if wej['uczciwie'] else ""}.
""")

    dobowo = st.radio("Widok", ["dobowo", "godzinowo"], horizontal=True, key="ps_widok") == "dobowo"
    Wykresy.show(fig_zuzycie_pogoda(t, dobowo), key="ps_pogoda")
    st.caption("Zielone romby to prognoza deszczu wydana dzień wcześniej – z niej korzysta model. Niebieskie słupki to deszcz, "
               "który naprawdę spadł. Gdy prognoza deszczu się myli, myli się też prognoza zużycia.")
    Wykresy.show(fig_jutro_pogoda(t), key="ps_jutro")

    if met:
        st.markdown("#### Porównanie z prostymi metodami (te same doby)")
        opisy = {"model": "nasza prognoza", "naiwny_doba": "„jutro jak dziś” (wczoraj o tej godzinie)",
                 "naiwny_tydzien": "„jak tydzień temu”", "profil_4tyg": "typowy dzień z 4 tygodni (mediana)"}
        p = met.get("porownanie_WAPE_doba", {})
        st.dataframe(pd.DataFrame([dict(metoda=opisy.get(k, k), średni_błąd_dobowy_proc=v,
                                        nasza_lepsza_o_proc=None if k == "model" else round(100 * (1 - p["model"] / v)))
                                   for k, v in p.items()]), width="stretch", hide_index=True)
    _, _, _, waz = wczytaj_wyniki()
    if waz is not None:
        Wykresy.show(Wykresy.fig_waznosc(waz), key="ps_waznosc")
        st.caption("Ważność cech modelu głównego (z treningu): najwięcej mówi historia zużycia, potem kalendarz i prognoza pogody.")
    if mies is not None and len(mies):
        with st.expander("Sumy miesięczne"):
            st.dataframe(mies.rename(columns={"kwh": "rzeczywiste [kWh]", "prognoza": "prognoza [kWh]",
                                              "roznica_proc": "różnica [%]"}).round(1), width="stretch")
    out = t.assign(czas=t["czas_lokalny"].dt.strftime("%Y-%m-%d %H:%M")).drop(columns=["czas_lokalny"])
    out = out[["czas", "rzeczywiste_kwh", "prognoza_kwh", "opad_mm", "prognoza_opadu_mm", "temperatura_c", "dzien_wolny",
               "swieto", "jutro"]].round(3)
    Narzedzia.przycisk_pobierania("Dane użyte do prognozy – godzinowo (CSV)", Narzedzia.to_csv_bytes(out),
                                  f"dane_wejsciowe_{oid}.csv", "text/csv", key="ps_csv")
