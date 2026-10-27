"""
Zakladka Wody przypadkowe – GLOWNY TEMAT: infiltracja i doplyw opadowy (nielegalne podlaczenia) w kanalizacji
rozdzielczej dla pompowni z pliku CSV, energia zuzywana przez wody przypadkowe i jej korelacja z opadem.
Reguly (baza bezdeszczowa, przeplyw nocny, reakcja na mm deszczu) - szczegoly w backend_ml_llm/wody_przypadkowe.py.
Wykrywanie nietypowych dni modelami ML (IF + LOF + SVM) - zakladki Detekcja anomalii i Anomalie.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from backend_ml_llm import anomalie_klient as A
from backend_ml_llm import wody_przypadkowe as W
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.styles import COL_ACCENT, COL_ANOM, COL_PRIMARY
from frontend_streamlit.wykresy import Wykresy

KOLOR_OCENY = {"wysoka": "#C00000", "silny": "#C00000", "umiarkowana": "#ED7D31", "umiarkowany": "#ED7D31",
               "niska": "#217346", "słaby": "#217346", "brak danych": "#8C8C8C"}


def _dane(d, dp):
    """Bilans i zdarzenia wód przypadkowych pompowni z pliku CSV (okres z pliku). Liczone raz na plik i pompownię."""
    oid, nowe, stacja = dp["oid"], dp["nowe"], dp.get("stacja")
    klucz = (dp["zrodlo"], oid, stacja)
    if st.session_state.get("wp_klucz") != klucz:
        with st.spinner("Obliczanie bilansu i zdarzeń..."):
            dd = A.dane_obiektu(d, oid, nowe)
            if stacja and oid not in set(d["obiekty"]["obiekt_id"]):
                dd["obiekty"].loc[dd["obiekty"]["obiekt_id"] == oid, "stacja_pogody"] = stacja
            dd = dict(dd, energia=dd["energia"][dd["energia"]["obiekt_id"] == oid])
            dz = W.dobowo(dd)
            zd, szereg = W.zdarzenia_obiektu(dd, dz, oid)
            lok = nowe["czas"].dt.tz_convert("Europe/Warsaw")
            od, do = pd.Timestamp(lok.min().date()), pd.Timestamp(lok.max().date())
            dz = dz[(dz["dzien"] >= od) & (dz["dzien"] <= do)]
            if len(zd):
                zd = zd[(pd.to_datetime(zd["dzien"]) >= od) & (pd.to_datetime(zd["dzien"]) <= do)].reset_index(drop=True)
            st.session_state.wp_klucz = klucz
            st.session_state.wp_dz, st.session_state.wp_rank = dz, W.ranking(dz)
            st.session_state.wp_zd, st.session_state.wp_szereg = zd, szereg
    return st.session_state.wp_dz, st.session_state.wp_rank


def _fig_ranking(r):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=r["obiekt"], y=r.get("udzial_wod_proc"), name="udział w objętości ścieków [%]",
                         marker_color=COL_PRIMARY, text=r.get("udzial_wod_proc").round(0), textposition="outside"))
    fig.add_trace(go.Bar(x=r["obiekt"], y=r.get("energia_wod_proc"), name="udział w zużyciu energii [%]",
                         marker_color=COL_ANOM, text=r.get("energia_wod_proc").round(0), textposition="outside"))
    fig.update_layout(barmode="group")
    return Wykresy.style_fig(fig, "Wody przypadkowe – udział w objętości ścieków i w zużyciu energii pompowni", None, "%", height=380)


def _fig_przeplyw(g, kol, baza, jedn, anom):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=g["dzien"], y=g["opad_doba"], name="opad", marker_color="rgba(88,178,227,0.4)"),
                  secondary_y=True)
    fig.add_trace(go.Scatter(x=g["dzien"], y=g[baza], name="baza bezdeszczowa", mode="lines",
                             line=dict(color=COL_ACCENT, width=1.6)), secondary_y=False)
    fig.add_trace(go.Scatter(x=g["dzien"], y=g[kol], name="rzeczywiste", mode="lines", line=dict(color="#1A1A1A", width=1.1),
                             fill="tonexty", fillcolor="rgba(192,0,0,0.15)"), secondary_y=False)
    if anom is not None and len(anom):
        a = g[["dzien", kol]].merge(anom[anom["anomalia"] == True][["dzien", "typ"]], on="dzien")
        if len(a):
            fig.add_trace(go.Scatter(x=a["dzien"], y=a[kol], mode="markers", name="anomalia ML",
                                     marker=dict(color=COL_ANOM, size=7, symbol="x"), text=a["typ"],
                                     hovertemplate="%{x|%d.%m.%Y}<br>%{text}<extra></extra>"), secondary_y=False)
    fig = Wykresy.style_fig(fig, f"{'Przepływ' if jedn == 'm³' else 'Energia'} dobowo vs baza bezdeszczowa", None, f"{jedn}/doba", height=430)
    fig.update_yaxes(title_text="mm", secondary_y=True, showgrid=False, autorange="reversed")
    return fig


def _fig_korelacja(g, kol, jedn, nazwa):
    m = g[g["opad_doba"] >= 0.1].dropna(subset=[kol])
    fig = go.Figure(go.Scatter(x=m["opad_doba"], y=m[kol], mode="markers", marker=dict(color=COL_PRIMARY, size=6, opacity=0.55),
                               hovertemplate="%{x:.1f} mm<br>%{y:.0f} " + jedn + "<extra></extra>", name="doby z opadem"))
    a, b, r = W._regresja(m.loc[m["opad_doba"] >= W.MOKRY_MM, "opad_doba"].values,
                          m.loc[m["opad_doba"] >= W.MOKRY_MM, kol].values)
    if np.isfinite(a):
        x = np.linspace(W.MOKRY_MM, m["opad_doba"].max(), 20)
        fig.add_trace(go.Scatter(x=x, y=a * x + b, mode="lines", line=dict(color=COL_ANOM, width=2),
                                 name=f"{a:.1f} {jedn} na 1 mm, r = {r:.2f}"))
    return Wykresy.style_fig(fig, f"{nazwa}: nadwyżka vs opad", "opad [mm/doba]", f"nadwyżka [{jedn}]", height=380)


def _fig_noc(g):
    s = g.dropna(subset=["noc_udzial"]).set_index("dzien")["noc_udzial"]
    sucho = s[g.set_index("dzien").loc[s.index, "opad_3d"] < W.SUCHY_3D_MM]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s.rolling(30, min_periods=10).median(), mode="lines", name="mediana 30 dni",
                             line=dict(color="#1A1A1A", width=1.6)))
    fig.add_trace(go.Scatter(x=sucho.index, y=sucho, mode="markers", name="doby suche", marker=dict(size=4, color=COL_PRIMARY, opacity=0.5)))
    for prog, op in ((W.PROG_NOC[0], "umiarkowana"), (W.PROG_NOC[1], "wysoka")):
        fig.add_hline(y=prog, line=dict(color=KOLOR_OCENY[op], dash="dash"), annotation_text=f"infiltracja {op}")
    return Wykresy.style_fig(fig, "Infiltracja: przepływ nocny / średni", None, "udział", height=340)


def _fig_zdarzenie(s, z):
    """Godzinowo ±12 h wokół zdarzenia: rzeczywiste vs baza bezdeszczowa, opad, godziny zdarzenia zaznaczone."""
    t0 = pd.Timestamp(z["poczatek"]).tz_localize("Europe/Warsaw").tz_convert("UTC") - pd.Timedelta(hours=12)
    t1 = pd.Timestamp(z["koniec"]).tz_localize("Europe/Warsaw").tz_convert("UTC") + pd.Timedelta(hours=12)
    w = s[(s["czas"] >= t0) & (s["czas"] <= t1)]
    lok = w["czas"].dt.tz_convert("Europe/Warsaw")
    jedn = "m³/h" if w["jednostka"].iloc[0] == "m3" else "kWh/h"
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=lok, y=w["opad_mm"], name="opad [mm/h]", marker_color="rgba(88,178,227,0.45)"), secondary_y=True)
    fig.add_trace(go.Scatter(x=lok, y=w["baza"], name="baza bezdeszczowa", line=dict(color=COL_ACCENT, width=1.8)), secondary_y=False)
    fig.add_trace(go.Scatter(x=lok, y=w["wartosc"], name="rzeczywiste", line=dict(color="#1A1A1A", width=1.4), fill="tonexty",
                             fillcolor="rgba(192,0,0,0.15)"), secondary_y=False)
    fig.add_vrect(x0=z["poczatek"], x1=z["koniec"], fillcolor="rgba(192,0,0,0.08)", line_width=0, annotation_text="zdarzenie")
    fig = Wykresy.style_fig(fig, f"Zdarzenie {z['dzien']} {z['godziny']}", None, jedn, height=400)
    fig.update_yaxes(title_text="mm/h", secondary_y=True, showgrid=False, autorange="reversed")
    return fig


def renderuj():
    st.subheader("Wody przypadkowe")
    st.caption("Nadwyżka ponad ścieki bytowe: **infiltracja** (stały dopływ, widoczny w nocy) i **dopływ opadowy** "
               "(nielegalne podłączenia, skok w deszczu).")
    d = st.session_state.get("d_baza")
    if d is None:
        st.warning("Dane referencyjne (pogoda, kalendarz) nie zostały załadowane. Odśwież stronę.")
        return
    dp = st.session_state.get("dane_prognozy")
    if dp is None:
        st.info("Wgraj plik CSV z zużyciem energii w panelu bocznym i kliknij **Wczytaj pliki**.")
        return
    oid = dp["oid"]
    st.markdown(f"**{dp['zrodlo']}** · pompownia **{oid}**")
    try:
        dz, rank = _dane(d, dp)
    except Exception as e:
        st.error(f"Błąd obliczeń: {e}")
        return
    if dz.empty or rank.empty:
        st.warning("Plik zawiera zbyt mało danych do obliczenia bilansu wód przypadkowych.")
        return

    cena = st.number_input("Cena energii [zł/kWh]", min_value=0.0, value=W.CENA_ZL_KWH, step=0.1, key="wp_cena",
                           help="Stała cena wg organizatorów: 1 zł/kWh.")
    zd = st.session_state.wp_zd.copy()
    if len(zd):
        zd["koszt_zl"] = (zd["nadwyzka_kwh"] * cena).round(2)

    # ------------------------------------------------------------------ podsumowanie pompowni
    r = rank.iloc[0].to_dict()
    g = dz.sort_values("dzien")
    przeplyw = bool(r.get("przeplywomierz"))
    kol, baza, nad, jedn = ("m3", "m3_baza", "nadwyzka_m3", "m³") if przeplyw else ("kwh", "kwh_baza", "nadwyzka_kwh", "kWh")
    c1, c2, c3, c4 = st.columns(4)
    if przeplyw:
        c1.metric("Wody przypadkowe", f"{r['udzial_wod_proc']:.0f}% objętości",
                  f"{r['wody_m3_rok']:,.0f} m³ rocznie".replace(",", " "), delta_color="off")
    elif pd.notna(r.get("energia_wod_proc")):
        c1.metric("Wody przypadkowe", f"{r['energia_wod_proc']:.0f}% energii", "bez przepływomierza", delta_color="off")
    c2.metric("Infiltracja", r["infiltracja"],
              f"przepływ nocny {r['noc_sucho']:.2f} średniego" if pd.notna(r.get("noc_sucho")) else None, delta_color="off")
    c3.metric("Dopływ opadowy", r["doplyw_opadowy"],
              f"+{r['reakcja_proc_na_mm']:.1f}% na 1 mm" if pd.notna(r.get("reakcja_proc_na_mm")) else None, delta_color="off")
    if pd.notna(r.get("energia_wod_kwh_rok")):
        c4.metric("Energia na wody", f"{r['energia_wod_kwh_rok']:,.0f} kWh/rok".replace(",", " "),
                  f"≈ {r['energia_wod_kwh_rok'] * cena:,.0f} zł rocznie".replace(",", " "), delta_color="off")
    st.markdown(W.opis(r))

    tab = rank.assign(
        **{"wody przypadkowe [% objętości]": rank.get("udzial_wod_proc"), "m³ rocznie": rank.get("wody_m3_rok"),
           "przepływ nocny / średni (suche dni)": rank.get("noc_sucho"), "infiltracja": rank["infiltracja"],
           "reakcja na 1 mm [% bazy]": rank.get("reakcja_proc_na_mm"), "dopływ opadowy (podłączenia)": rank["doplyw_opadowy"],
           "energia na wody [%]": rank.get("energia_wod_proc"), "kWh rocznie": rank.get("energia_wod_kwh_rok"),
           "kWh na 1 mm": rank.get("reakcja_kwh_na_mm"), "korelacja opad ↔ energia": rank.get("korelacja_opad_kwh"),
           "koszt [zł/rok]": rank["energia_wod_kwh_rok"] * cena if "energia_wod_kwh_rok" in rank else None})
    kol_tab = ["obiekt", "wody przypadkowe [% objętości]", "m³ rocznie", "przepływ nocny / średni (suche dni)", "infiltracja",
           "reakcja na 1 mm [% bazy]", "dopływ opadowy (podłączenia)", "energia na wody [%]", "kWh rocznie", "koszt [zł/rok]",
           "kWh na 1 mm", "korelacja opad ↔ energia"]
    st.dataframe(tab[kol_tab].round(2), width="stretch", hide_index=True)
    st.caption(f"Infiltracja (przepływ nocny / średni, suche dni): < {W.PROG_NOC[0]} niska, > {W.PROG_NOC[1]} wysoka. "
               f"Dopływ opadowy (% bazy na 1 mm): < {W.PROG_REAKCJI[0]}% słaby, > {W.PROG_REAKCJI[1]}% silny. Progi orientacyjne.")

    # ------------------------------------------------------------------ wykresy
    an = st.session_state.get("an_wynik")                       # nietypowe doby ML z zakladki Anomalie (ta sama pompownia)
    anom = an["g"] if an is not None and an["meta"]["obiekt"] == oid else None
    Wykresy.show(_fig_przeplyw(g, kol, baza, jedn, anom), key="wp_seria")
    c1, c2 = st.columns(2)
    with c1:
        Wykresy.show(_fig_korelacja(g, nad, jedn, "Dopływ opadowy"), key="wp_kor")
    with c2:
        if g["kwh"].notna().any():
            Wykresy.show(_fig_korelacja(g, "nadwyzka_kwh", "kWh", "Energia"), key="wp_kor_kwh")
    if przeplyw:
        Wykresy.show(_fig_noc(g), key="wp_noc")

    # ------------------------------------------------------------------ zdarzenia (format organizatorów)
    st.divider()
    st.markdown("### Zdarzenia")
    st.caption(f"Zdarzenie: ≥ {W.MIN_GODZIN} h z nadwyżką ≥ {W.PROG_PROC:.0f}% ponad bazę godzinową. "
               f"„Dopływ opadowy”: ≥ 1 mm opadu w trakcie lub {W.OKNO_OPADU_H} h przed.")
    if len(zd):
        ps = W.podsumowanie_zdarzen(zd).rename(columns={"obiekt": "pompownia", "zdarzen": "zdarzeń", "opadowych": "w czasie opadu",
                                                        "po_opadach": "po opadach", "bez_opadu": "bez opadu",
                                                        "dni_ze_zdarzeniami": "dni", "godzin": "godzin", "objetosc_m3": "objętość [m³]",
                                                        "nadwyzka_kwh": "nadwyżka energii [kWh]", "koszt_zl": "koszt [zł]"})
        st.dataframe(ps.round(0), width="stretch", hide_index=True)
        typy = st.multiselect("Typ", sorted(zd["typ"].unique()), default=sorted(zd["typ"].unique()), key="wp_typy")
        zo = zd[zd["typ"].isin(typy)].sort_values("poczatek", ascending=False)
        widok = zo.rename(columns={"dzien": "dzień", "godziny": "godziny", "czas_trwania_h": "godzin", "objetosc_m3": "objętość [m³]",
                                   "nadwyzka_kwh": "energia [kWh]", "koszt_zl": "koszt [zł]", "opad_mm": "opad [mm]",
                                   "max_opad_mm_h": "max [mm/h]"})
        st.dataframe(widok[["dzień", "godziny", "godzin", "objętość [m³]", "energia [kWh]", "koszt [zł]", "opad [mm]", "max [mm/h]", "typ"]],
                     width="stretch", hide_index=True, height=300)
        etyk = [f"{z.dzien} {z.godziny} · {z.objetosc_m3 if pd.notna(z.objetosc_m3) else z.nadwyzka_kwh} "
                f"{'m³' if pd.notna(z.objetosc_m3) else 'kWh'} · {z.typ}" for z in zo.itertuples()]
        if etyk:
            i = st.selectbox("Zdarzenie godzinowo", range(len(etyk)), format_func=lambda k: etyk[k], key="wp_zd_wybor")
            Wykresy.show(_fig_zdarzenie(st.session_state.wp_szereg, zo.iloc[i]), key="wp_zd_wykres")
        c1, c2 = st.columns(2)
        with c1:
            Narzedzia.przycisk_pobierania("Zdarzenia (Excel)", W.excel_zdarzen(zd, cena), f"zdarzenia_wod_przypadkowych_{oid}.xlsx",
                                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="wp_xlsx")
        with c2:
            Narzedzia.przycisk_pobierania("Zdarzenia (CSV)", Narzedzia.to_csv_bytes(zd.drop(columns=["poczatek", "koniec"])),
                                          f"zdarzenia_wod_przypadkowych_{oid}.csv", "text/csv", key="wp_zd_csv")
    else:
        st.info("W okresie z pliku nie wykryto zdarzeń wód przypadkowych.")

    suche, mokre, kol_n, jedn_n = W.dni_do_sprawdzenia(g)
    c1, c2 = st.columns(2)
    for c, df, tytul in ((c1, suche, "Suche dni – największa nadwyżka"),
                         (c2, mokre, "Deszczowe dni – największa nadwyżka")):
        with c:
            st.markdown(f"**{tytul}**")
            st.dataframe(df.assign(dzień=df["dzien"].dt.strftime("%d.%m.%Y"))[["dzień", "opad_doba", kol_n]].rename(
                columns={"opad_doba": "opad [mm]", kol_n: f"nadwyżka [{jedn_n}]"}).round(1), width="stretch", hide_index=True)
    st.caption("Anomalie ML pojawią się na wykresie po **Wykryj anomalie** w zakładce Anomalie.")
    Narzedzia.przycisk_pobierania("Bilans (CSV)", Narzedzia.to_csv_bytes(tab[kol_tab].round(3)),
                                  f"wody_przypadkowe_{oid}.csv", "text/csv", key="wp_csv_rank")
