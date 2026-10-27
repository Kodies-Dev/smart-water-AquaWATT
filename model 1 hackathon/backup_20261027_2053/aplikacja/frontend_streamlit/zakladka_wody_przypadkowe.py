"""
Zakladka Wody przypadkowe – GLOWNY TEMAT: infiltracja i doplyw opadowy (nielegalne podlaczenia) w kanalizacji
rozdzielczej, ranking pompowni, energia zuzywana przez wody przypadkowe i jej korelacja z opadem.
Reguly (baza bezdeszczowa, przeplyw nocny, reakcja na mm deszczu) - szczegoly w backend_ml_llm/wody_przypadkowe.py.
Wykrywanie nietypowych dni modelami ML (IF + LOF + SVM) - zakladki Detekcja anomalii i Anomalie.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from backend_ml_llm import wody_przypadkowe as W
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.styles import COL_ACCENT, COL_ANOM, COL_PRIMARY
from frontend_streamlit.wykresy import Wykresy

KOLOR_OCENY = {"wysoka": "#C00000", "silny": "#C00000", "umiarkowana": "#ED7D31", "umiarkowany": "#ED7D31",
               "niska": "#217346", "słaby": "#217346", "brak danych": "#8C8C8C"}


def _dane():
    d = st.session_state.get("d_baza")
    if d is None:
        return None, None, None
    if st.session_state.get("wp_dz") is None:
        with st.spinner("Liczę bilans i zdarzenia wód przypadkowych dla wszystkich pompowni..."):
            dz = W.dobowo(d)
            st.session_state.wp_dz = dz
            st.session_state.wp_rank = W.ranking(dz)
            st.session_state.wp_anom = W.anomalie_z_bazy()
            st.session_state.wp_zd, st.session_state.wp_szeregi = W.zdarzenia(d, dz)
    return st.session_state.wp_dz, st.session_state.wp_rank, st.session_state.wp_anom


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
    fig.add_trace(go.Bar(x=g["dzien"], y=g["opad_doba"], name="opad [mm/doba]", marker_color="rgba(46,117,182,0.35)"),
                  secondary_y=True)
    fig.add_trace(go.Scatter(x=g["dzien"], y=g[baza], name="baza bezdeszczowa (same ścieki bytowe)", mode="lines",
                             line=dict(color=COL_ACCENT, width=1.6)), secondary_y=False)
    fig.add_trace(go.Scatter(x=g["dzien"], y=g[kol], name="rzeczywiste", mode="lines", line=dict(color="#1A1A1A", width=1.1),
                             fill="tonexty", fillcolor="rgba(192,0,0,0.15)"), secondary_y=False)
    if anom is not None and len(anom):
        a = g.merge(anom[anom["anomalia"] == True][["dzien", "typ"]], on="dzien")
        if len(a):
            fig.add_trace(go.Scatter(x=a["dzien"], y=a[kol], mode="markers", name="anomalia (IF+LOF+SVM)",
                                     marker=dict(color=COL_ANOM, size=7, symbol="x"), text=a["typ"],
                                     hovertemplate="%{x|%d.%m.%Y}<br>%{text}<extra></extra>"), secondary_y=False)
    fig = Wykresy.style_fig(fig, f"Dobowy {'przepływ' if jedn == 'm³' else 'pobór energii'} vs baza bezdeszczowa – "
                                 f"czerwone pole = wody przypadkowe", None, f"{jedn} / doba", height=430)
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
    return Wykresy.style_fig(fig, f"{nazwa}: nadwyżka ponad bazę vs opad dobowy", "opad [mm / doba]", f"nadwyżka [{jedn}]", height=380)


def _fig_noc(g):
    s = g.dropna(subset=["noc_udzial"]).set_index("dzien")["noc_udzial"]
    sucho = s[g.set_index("dzien").loc[s.index, "opad_3d"] < W.SUCHY_3D_MM]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s.rolling(30, min_periods=10).median(), mode="lines", name="mediana 30 dni",
                             line=dict(color="#1A1A1A", width=1.6)))
    fig.add_trace(go.Scatter(x=sucho.index, y=sucho, mode="markers", name="doby suche", marker=dict(size=4, color=COL_PRIMARY, opacity=0.5)))
    for prog, op in ((W.PROG_NOC[0], "umiarkowana"), (W.PROG_NOC[1], "wysoka")):
        fig.add_hline(y=prog, line=dict(color=KOLOR_OCENY[op], dash="dash"), annotation_text=f"infiltracja {op}")
    return Wykresy.style_fig(fig, "Infiltracja: przepływ nocny (02–05) / średni przepływ doby", None, "udział", height=340)


def _fig_zdarzenie(s, z):
    """Godzinowo ±12 h wokół zdarzenia: rzeczywiste vs baza bezdeszczowa, opad, godziny zdarzenia zaznaczone."""
    t0 = pd.Timestamp(z["poczatek"]).tz_localize("Europe/Warsaw").tz_convert("UTC") - pd.Timedelta(hours=12)
    t1 = pd.Timestamp(z["koniec"]).tz_localize("Europe/Warsaw").tz_convert("UTC") + pd.Timedelta(hours=12)
    w = s[(s["czas"] >= t0) & (s["czas"] <= t1)]
    lok = w["czas"].dt.tz_convert("Europe/Warsaw")
    jedn = "m³/h" if w["jednostka"].iloc[0] == "m3" else "kWh/h"
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=lok, y=w["opad_mm"], name="opad [mm/h]", marker_color="rgba(46,117,182,0.4)"), secondary_y=True)
    fig.add_trace(go.Scatter(x=lok, y=w["baza"], name="baza bezdeszczowa", line=dict(color=COL_ACCENT, width=1.8)), secondary_y=False)
    fig.add_trace(go.Scatter(x=lok, y=w["wartosc"], name="rzeczywiste", line=dict(color="#1A1A1A", width=1.4), fill="tonexty",
                             fillcolor="rgba(192,0,0,0.15)"), secondary_y=False)
    fig.add_vrect(x0=z["poczatek"], x1=z["koniec"], fillcolor="rgba(192,0,0,0.08)", line_width=0, annotation_text="zdarzenie")
    fig = Wykresy.style_fig(fig, f"Zdarzenie {z['dzien']} {z['godziny']} – godzina po godzinie", None, jedn, height=400)
    fig.update_yaxes(title_text="mm/h", secondary_y=True, showgrid=False, autorange="reversed")
    return fig


def renderuj():
    st.subheader("Wody przypadkowe w kanalizacji rozdzielczej")
    st.markdown("W kanalizacji rozdzielczej do pompowni powinny płynąć **tylko ścieki z domów**. Każdy dodatkowy m³ to "
                "**wody przypadkowe**: **infiltracja** (wody gruntowe przez nieszczelne rury – stały dopływ, widoczny w nocy) "
                "i **dopływ opadowy** z **nielegalnych podłączeń** rynien i odwodnień (skok przepływu w dniu deszczu). "
                "Pompy muszą je przepompować – płacimy za to energią.")
    dz, rank, anom = _dane()
    if dz is None:
        st.warning("Brak danych z bazy – uruchom bazę (docker compose up -d db) i odśwież stronę.")
        return

    cena = st.number_input("Cena energii [zł/kWh]", min_value=0.0, value=W.CENA_ZL_KWH, step=0.1, key="wp_cena",
                           help="Organizatorzy: PWiK Rybnik ma stałą cenę energii – do obliczeń 1 zł/kWh.")
    zd = st.session_state.wp_zd.copy() if st.session_state.get("wp_zd") is not None else pd.DataFrame()
    if len(zd):
        zd["koszt_zl"] = (zd["nadwyzka_kwh"] * cena).round(2)

    # ------------------------------------------------------------------ podsumowanie i ranking
    z = rank[rank["przeplywomierz"]]
    c1, c2, c3, c4 = st.columns(4)
    if len(z):
        naj = z.iloc[0]
        c1.metric("Najwięcej wód przypadkowych", f"{naj['obiekt']}", f"{naj['udzial_wod_proc']:.0f}% objętości", delta_color="off")
        inf = z.sort_values("noc_sucho", ascending=False).iloc[0]
        c2.metric("Najsilniejsza infiltracja", f"{inf['obiekt']}", f"przepływ nocny {inf['noc_sucho']:.2f} średniego", delta_color="off")
        dop = rank.sort_values("reakcja_proc_na_mm", ascending=False).iloc[0]
        c3.metric("Najsilniej reaguje na deszcz", f"{dop['obiekt']}", f"+{dop['reakcja_proc_na_mm']:.1f}% na 1 mm", delta_color="off")
    if "energia_wod_kwh_rok" in rank:
        c4.metric("Energia na wody przypadkowe", f"{rank['energia_wod_kwh_rok'].sum():,.0f} kWh/rok".replace(",", " "),
                  f"≈ {rank['energia_wod_kwh_rok'].sum() * cena:,.0f} zł rocznie".replace(",", " "), delta_color="off")
    Wykresy.show(_fig_ranking(rank), key="wp_ranking")

    tab = rank.assign(
        **{"wody przypadkowe [% objętości]": rank.get("udzial_wod_proc"), "m³ rocznie": rank.get("wody_m3_rok"),
           "przepływ nocny / średni (suche dni)": rank.get("noc_sucho"), "infiltracja": rank["infiltracja"],
           "reakcja na 1 mm [% bazy]": rank.get("reakcja_proc_na_mm"), "dopływ opadowy (podłączenia)": rank["doplyw_opadowy"],
           "energia na wody [%]": rank.get("energia_wod_proc"), "kWh rocznie": rank.get("energia_wod_kwh_rok"),
           "kWh na 1 mm": rank.get("reakcja_kwh_na_mm"), "korelacja opad ↔ energia": rank.get("korelacja_opad_kwh"),
           "koszt [zł/rok]": rank.get("energia_wod_kwh_rok") * cena})
    kol_tab = ["obiekt", "wody przypadkowe [% objętości]", "m³ rocznie", "przepływ nocny / średni (suche dni)", "infiltracja",
           "reakcja na 1 mm [% bazy]", "dopływ opadowy (podłączenia)", "energia na wody [%]", "kWh rocznie", "koszt [zł/rok]",
           "kWh na 1 mm", "korelacja opad ↔ energia"]
    st.dataframe(tab[kol_tab].round(2), width="stretch", hide_index=True)
    st.caption(f"Infiltracja z przepływu nocnego w suche dni: < {W.PROG_NOC[0]} niska, {W.PROG_NOC[0]}–{W.PROG_NOC[1]} umiarkowana, "
               f"> {W.PROG_NOC[1]} wysoka (dla samych ścieków bytowych zwykle 0,3–0,45). Dopływ opadowy z nadwyżki na 1 mm deszczu: "
               f"< {W.PROG_REAKCJI[0]}% słaby, do {W.PROG_REAKCJI[1]}% umiarkowany, wyżej silny. Progi orientacyjne. Pompownie bez "
               f"przepływomierza oceniane po energii.")

    # ------------------------------------------------------------------ zdarzenia (format organizatorów)
    st.divider()
    st.markdown("### Zdarzenia wód przypadkowych – dzień, godziny wystąpienia, objętość")
    st.caption(f"Godzina z wodami przypadkowymi: przepływ (bez przepływomierza – energia) ≥ {W.PROG_PROC:.0f}% ponad godzinową bazę "
               f"bezdeszczową i ponad {W.PROG_MAD:.0f} odchylenia typowe z suchych godzin; zdarzenie = ≥ {W.MIN_GODZIN} kolejne godziny. "
               f"Typ „dopływ opadowy”, gdy w trakcie lub {W.OKNO_OPADU_H} h przed spadł ≥ 1 mm deszczu. Okres błędnej kalibracji "
               f"przepływomierza RY_PZ1 (III 2024) odrzucony, zgodnie z zaleceniem organizatorów.")
    if len(zd):
        ps = W.podsumowanie_zdarzen(zd).rename(columns={"obiekt": "pompownia", "zdarzen": "zdarzeń", "opadowych": "opadowych",
                                                        "bez_opadu": "bez opadu", "godzin": "godzin", "objetosc_m3": "objętość [m³]",
                                                        "nadwyzka_kwh": "nadwyżka energii [kWh]", "koszt_zl": "koszt [zł]"})
        st.dataframe(ps.round(0), width="stretch", hide_index=True)
        c1, c2 = st.columns(2)
        with c1:
            Narzedzia.przycisk_pobierania("Zdarzenia – wszystkie pompownie (Excel)", W.excel_zdarzen(zd, cena),
                                          "zdarzenia_wod_przypadkowych.xlsx",
                                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="wp_xlsx")
        with c2:
            Narzedzia.przycisk_pobierania("Zdarzenia – wszystkie pompownie (CSV)",
                                          Narzedzia.to_csv_bytes(zd.drop(columns=["poczatek", "koniec"])),
                                          "zdarzenia_wod_przypadkowych.csv", "text/csv", key="wp_zd_csv")

    # ------------------------------------------------------------------ jedna pompownia
    st.divider()
    obiekty = list(rank["obiekt"])
    oid = st.selectbox("Pompownia", obiekty, key="wp_obiekt")
    r = rank.set_index("obiekt").loc[oid].to_dict()
    g = dz[dz["obiekt_id"] == oid].sort_values("dzien")
    przeplyw = bool(r.get("przeplywomierz"))
    kol, baza, nad, jedn = ("m3", "m3_baza", "nadwyzka_m3", "m³") if przeplyw else ("kwh", "kwh_baza", "nadwyzka_kwh", "kWh")
    st.markdown(f"#### {oid}")
    st.markdown(W.opis(r))
    Wykresy.show(_fig_przeplyw(g, kol, baza, jedn, anom[anom["obiekt_id"] == oid] if anom is not None else None), key="wp_seria")
    c1, c2 = st.columns(2)
    with c1:
        Wykresy.show(_fig_korelacja(g, nad, jedn, "Dopływ opadowy"), key="wp_kor")
    with c2:
        if g["kwh"].notna().any():
            Wykresy.show(_fig_korelacja(g, "nadwyzka_kwh", "kWh", "Energia"), key="wp_kor_kwh")
    if przeplyw:
        Wykresy.show(_fig_noc(g), key="wp_noc")
    zo = zd[zd["obiekt"] == oid].sort_values("poczatek", ascending=False) if len(zd) else pd.DataFrame()
    if len(zo):
        st.markdown(f"#### Zdarzenia {oid} ({len(zo)}; opadowych {int((zo['typ'] == 'dopływ opadowy').sum())})")
        typy = st.multiselect("Typ", sorted(zo["typ"].unique()), default=sorted(zo["typ"].unique()), key="wp_typy")
        zo = zo[zo["typ"].isin(typy)]
        widok = zo.rename(columns={"dzien": "dzień", "godziny": "godziny", "czas_trwania_h": "godzin", "objetosc_m3": "objętość [m³]",
                                   "nadwyzka_kwh": "energia [kWh]", "koszt_zl": "koszt [zł]", "opad_mm": "opad [mm]",
                                   "max_opad_mm_h": "max [mm/h]"})
        st.dataframe(widok[["dzień", "godziny", "godzin", "objętość [m³]", "energia [kWh]", "koszt [zł]", "opad [mm]", "max [mm/h]", "typ"]],
                     width="stretch", hide_index=True, height=300)
        etyk = [f"{r.dzien} {r.godziny} · {r.objetosc_m3 if pd.notna(r.objetosc_m3) else r.nadwyzka_kwh} "
                f"{'m³' if pd.notna(r.objetosc_m3) else 'kWh'} · {r.typ}" for r in zo.itertuples()]
        if etyk:
            i = st.selectbox("Pokaż zdarzenie na wykresie godzinowym", range(len(etyk)), format_func=lambda k: etyk[k], key="wp_zd_wybor")
            Wykresy.show(_fig_zdarzenie(st.session_state.wp_szeregi[oid], zo.iloc[i]), key="wp_zd_wykres")
    suche, mokre, kol_n, jedn_n = W.dni_do_sprawdzenia(g)
    c1, c2 = st.columns(2)
    for c, df, tytul in ((c1, suche, "Największa nadwyżka w suche dni – sprawdzić infiltrację / awarię"),
                         (c2, mokre, "Największa nadwyżka w deszczowe dni – dopływ opadowy")):
        with c:
            st.markdown(f"**{tytul}**")
            st.dataframe(df.assign(dzień=df["dzien"].dt.strftime("%d.%m.%Y"))[["dzień", "opad_doba", kol_n]].rename(
                columns={"opad_doba": "opad [mm]", kol_n: f"nadwyżka [{jedn_n}]"}).round(1), width="stretch", hide_index=True)
    st.caption("Nietypowe dni wykryte modelami ML (Isolation Forest + LOF + One-Class SVM, walidacja na alarmach tłoczni) – "
               "zakładki **Detekcja anomalii** i **Anomalie**.")
    Narzedzia.przycisk_pobierania("Bilans wód przypadkowych – ranking (CSV)", Narzedzia.to_csv_bytes(tab[kol_tab].round(3)),
                                  "wody_przypadkowe_ranking.csv", "text/csv", key="wp_csv_rank")
