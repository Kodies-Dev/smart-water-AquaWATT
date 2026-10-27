"""
Zakladka Anomalie - widok dla klienta (jak zakladka Prognoza): dane z panelu albo pompownia z bazy, jeden przycisk,
wynik opisany prostym jezykiem (Python, bez LLM): zdarzenia wod przypadkowych (dzien, godziny, objetosc, koszt) i nietypowe
doby wskazane przez ML (IF + LOF + SVM), wykresy, Excel z wykresami.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend_ml_llm import anomalie_klient as A
from backend_ml_llm import wody_przypadkowe as W
from backend_ml_llm.raport_excel import raport_excel_anomalii
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.wykresy import Wykresy
from frontend_streamlit.zakladka_wody_przypadkowe import _fig_przeplyw, _fig_zdarzenie

KOLORY_TYPOW = {W.TYP_OPAD: "#2E75B6", W.TYP_PO: "#9DC3E6", W.TYP_BEZ: "#C00000"}
MIASTA = {"RY": "Rybnik", "RU": "Ruda Śląska", "CH": "Chorzów"}


def _fig_zdarzenia(zd, przeplyw):
    y, jedn = ("objetosc_m3", "m³") if przeplyw else ("nadwyzka_kwh", "kWh")
    fig = go.Figure()
    for typ, g in zd.groupby("typ"):
        fig.add_trace(go.Bar(x=pd.to_datetime(g["dzien"]), y=g[y], name=typ, marker_color=KOLORY_TYPOW.get(typ, "#8C8C8C"),
                             customdata=g[["godziny", "opad_mm"]], hovertemplate="%{x|%d.%m.%Y} %{customdata[0]}<br>%{y:.0f} " + jedn +
                             "<br>opad %{customdata[1]:.1f} mm<extra></extra>"))
    fig.update_layout(barmode="stack")
    return Wykresy.style_fig(fig, f"Zdarzenia wód przypadkowych – wielkość [{jedn} ponad bazę] (kolor = typ)", None, jedn, height=360)


def renderuj():
    st.subheader("Wykrywanie anomalii i wód przypadkowych")
    st.markdown("Jednym przyciskiem sprawdzamy, **kiedy i ile wód przypadkowych** dopłynęło do pompowni (dzień, godziny, objętość, "
                "koszt energii) i które doby były **nietypowe** według modeli uczenia maszynowego.")
    d = st.session_state.get("d_baza")
    if d is None:
        st.warning("Brak połączenia z bazą danych - uruchom bazę (`docker compose up -d db`) i odśwież stronę.")
        return
    dp = st.session_state.get("dane_prognozy")
    zrodla = (["Dane z panelu (okres z pliku)"] if dp is not None else []) + ["Pompownia z bazy (cała historia)"]
    zrodlo = st.radio("Dane", zrodla, horizontal=True, key="an_zrodlo",
                      help="Dane z panelu: plik z zużyciem energii pompowni (przepływ i SCADA - z bazy, jeśli są). "
                           "Pompownia z bazy: cała historia przepływu i energii.")
    if zrodlo.startswith("Dane z panelu"):
        oid, nowe, stacja = dp["oid"], dp["nowe"], dp.get("stacja")
        st.markdown(f"Dane: **{dp['zrodlo']}** · pompownia **{oid}** · zmienisz je w panelu po lewej.")
    else:
        obiekty = sorted(d["energia"]["obiekt_id"].unique())
        oid = st.selectbox("Pompownia", obiekty, key="an_obiekt", index=obiekty.index("RU_W") if "RU_W" in obiekty else 0)
        nowe, stacja = None, None
    with st.expander("Ustawienia zaawansowane"):
        odsetek = st.slider("Oczekiwany odsetek nietypowych dób (ML)", 0.02, 0.12, A.ODSETEK, 0.01, format="%.2f", key="an_odsetek",
                            help="5% dobrane na alarmach tłoczni Chorzów (python main.py anomalie). Więcej = czulszy detektor.")
        cena = st.number_input("Cena energii [zł/kWh]", min_value=0.0, value=W.CENA_ZL_KWH, step=0.1, key="an_cena",
                               help="Organizatorzy: stała cena 1 zł/kWh.")
    klucz = (zrodlo, oid, dp["zrodlo"] if dp is not None and zrodlo.startswith("Dane z panelu") else None, odsetek, cena)
    if st.button("Wykryj anomalie", type="primary", key="an_start"):
        with st.spinner("Liczę cechy dobowe, zdarzenia godzinowe i modele ML (ok. 20–40 s)..."):
            try:
                g, zd, sz, meta, wsz = A.wykryj(d, oid, nowe, odsetek, cena, stacja)
                st.session_state.an_wynik = dict(klucz=klucz, g=g, zd=zd, sz=sz, meta=meta, wszystkie=wsz)
            except Exception as e:
                st.error(f"Coś poszło nie tak: {e}")
    w = st.session_state.get("an_wynik")
    if w is None or w["klucz"] != klucz:
        return
    g, zd, sz, meta = w["g"], w["zd"], w["sz"], w["meta"]
    s = A.podsumuj(g, zd, meta)
    st.divider()
    st.markdown(f"### Wynik dla pompowni {oid}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Zdarzenia wód przypadkowych", f"{s['zdarzen']}", f"{s['opadowych'] + s['po_opadach']} związanych z deszczem",
              delta_color="off")
    c2.metric("Objętość ponad bazę", f"{s['objetosc']:,.0f} m³".replace(",", " ") if pd.notna(s["objetosc"]) else "– (brak przepływomierza)",
              f"{s['udzial']:.0f}% objętości" if pd.notna(s["udzial"]) else None, delta_color="off")
    c3.metric("Koszt energii", f"{s['koszt']:,.0f} zł".replace(",", " "), f"{s['kwh']:,.0f} kWh ponad bazę".replace(",", " "), delta_color="off")
    c4.metric("Nietypowe doby (ML)", f"{s['dni_ml']}", f"z {s['dob']} dób", delta_color="off")
    st.markdown(s["tekst"])
    przeplyw = bool(meta["przeplyw"])
    kol, baza, jedn = ("m3", "m3_baza", "m³") if przeplyw else ("kwh", "kwh_baza", "kWh")
    Wykresy.show(_fig_przeplyw(g, kol, baza, jedn, g), key="an_os")
    if len(zd):
        Wykresy.show(_fig_zdarzenia(zd, przeplyw), key="an_zd_wykres")
        st.markdown("#### Zdarzenia – dzień, godziny wystąpienia, objętość")
        widok = zd.sort_values("poczatek", ascending=False).rename(columns={
            "dzien": "dzień", "godziny": "godziny", "czas_trwania_h": "godzin", "objetosc_m3": "objętość [m³]",
            "nadwyzka_kwh": "energia [kWh]", "koszt_zl": "koszt [zł]", "opad_mm": "opad [mm]", "ml_typ": "typ wg ML"})
        st.dataframe(widok[["dzień", "godziny", "godzin", "objętość [m³]", "energia [kWh]", "koszt [zł]", "opad [mm]", "typ", "typ wg ML",
                            "zdarzenie"]],
                     width="stretch", hide_index=True, height=320)
        zs = zd.sort_values("poczatek", ascending=False).reset_index(drop=True)
        etyk = [f"{r.dzien} {r.godziny} · {r.objetosc_m3 if pd.notna(r.objetosc_m3) else r.nadwyzka_kwh} "
                f"{'m³' if pd.notna(r.objetosc_m3) else 'kWh'} · {r.typ}" for r in zs.itertuples()]
        i = st.selectbox("Pokaż zdarzenie godzina po godzinie", range(len(etyk)), format_func=lambda k: etyk[k], key="an_wybor")
        Wykresy.show(_fig_zdarzenie(sz, zs.iloc[i]), key="an_zd_godz")
    a = g[g["anomalia"] == True].sort_values("dzien", ascending=False)
    if len(a):
        with st.expander(f"Nietypowe doby wskazane przez ML ({len(a)})"):
            st.dataframe(a.assign(dzień=a["dzien"].dt.strftime("%d.%m.%Y"))[["dzień", "typ", "glosy", "opis"]].rename(
                columns={"glosy": "głosy (z 3)"}), width="stretch", hide_index=True)
    st.markdown("#### Pobierz wyniki")
    c1, c2 = st.columns(2)
    with c1:
        Narzedzia.przycisk_pobierania("Raport anomalii w Excelu (z wykresami)", raport_excel_anomalii(meta, s, g, zd, A.metoda(meta)),
                                      f"anomalie_{oid}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                      key="an_xlsx")
    with c2:
        if len(zd):
            Narzedzia.przycisk_pobierania("Zdarzenia (CSV)", Narzedzia.to_csv_bytes(zd.drop(columns=["poczatek", "koniec"])),
                                          f"zdarzenia_{oid}.csv", "text/csv", key="an_csv")
    st.caption("Na podstawie czego powstał wynik, jak głosowały modele i walidacja – zakładka **Anomalie – szczegóły**.")
