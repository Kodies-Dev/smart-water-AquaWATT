"""
Zakladka Anomalie - szczegoly (jak Prognoza - szczegoly): na podstawie czego powstal wynik, jak glosowaly modele
IF / LOF / SVM, typy i glowne przyczyny, infiltracja i korelacja z opadem, walidacja na alarmach i znanych zdarzeniach,
dane wejsciowe do pobrania.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend_ml_llm import anomalie_klient as A
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.styles import COL_ANOM, COL_PRIMARY, COL_ACCENT
from frontend_streamlit.wykresy import Wykresy
from frontend_streamlit.zakladka_wody_przypadkowe import _fig_korelacja, _fig_noc


def _slupki(seria, tytul, kolor=COL_PRIMARY, os_x=None):
    s = seria.sort_values()
    fig = go.Figure(go.Bar(x=s.values, y=s.index, orientation="h", marker_color=kolor, text=s.values, textposition="outside"))
    return Wykresy.style_fig(fig, tytul, os_x or "liczba dób", None, height=max(260, 40 * len(s) + 80))


def renderuj():
    w = st.session_state.get("an_wynik")
    if w is None:
        st.info("Szczegóły są dostępne po uruchomieniu analizy (**Wykryj anomalie**) w podzakładce **Anomalie**.")
        return
    g, zd, meta, wsz = w["g"], w["zd"], w["meta"], w["wszystkie"]
    oid = meta["obiekt"]
    st.markdown(f"#### {oid}, {meta['od']:%d.%m.%Y} – {meta['do']:%d.%m.%Y}")
    st.markdown(f"- **Dane:** {len(g)} dób z pliku"
                + (", z przepływomierzem" if meta["przeplyw"] else ", bez przepływomierza (liczone z energii)") + ".")
    for t in A.metoda(meta):
        st.markdown(f"- {t}")

    st.markdown("#### Głosowanie modeli")
    a = g[["IF", "LOF", "SVM"]].fillna(0).astype(int)
    glosy = a.sum(axis=1)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Isolation Forest", int(a["IF"].sum()))
    c2.metric("LOF", int(a["LOF"].sum()))
    c3.metric("One-Class SVM", int(a["SVM"].sum()))
    c4.metric("Zgoda ≥ 2 z 3 (wynik)", int((glosy >= 2).sum()))
    st.caption(f"1 model: {int((glosy == 1).sum())} · 2: {int((glosy == 2).sum())} · 3: {int((glosy == 3).sum())} dób. "
               f"Wynik = zgoda ≥ 2 z 3.")
    an = g[g["anomalia"] == True]
    if len(an):
        c1, c2 = st.columns(2)
        with c1:
            Wykresy.show(_slupki(an["typ"].value_counts(), "Typy", COL_ANOM), key="as_typy")
        with c2:
            pc = an["glowna_cecha"].map(lambda c: A.NAZWY_CECH.get(c, c)).value_counts()
            Wykresy.show(_slupki(pc, "Główna przyczyna"), key="as_przyczyny")
        if "Rodzaj_Anomalii" in an:
            st.caption("Rodzaj: " + ", ".join(f"{k}: {v}" for k, v in an["Rodzaj_Anomalii"].value_counts().items()))

    st.markdown("#### Opad a nadwyżka")
    przeplyw = bool(meta["przeplyw"])
    c1, c2 = st.columns(2)
    with c1:
        Wykresy.show(_fig_korelacja(g, "nadwyzka_m3" if przeplyw else "nadwyzka_kwh", "m³" if przeplyw else "kWh",
                                    "Przepływ" if przeplyw else "Energia"), key="as_kor")
    with c2:
        Wykresy.show(_fig_korelacja(g, "nadwyzka_kwh", "kWh", "Energia"), key="as_kor_kwh")
    if przeplyw and g["noc_udzial"].notna().sum() > 14:
        Wykresy.show(_fig_noc(g), key="as_noc")

    st.markdown("#### Walidacja detektora")
    from model.config import WYNIKI
    p = WYNIKI / "anomalie" / "walidacja_CH.csv"
    if p.exists():
        v = pd.read_csv(p)
        v = v[v["model"].astype(str).str.contains("zespół")]
        st.dataframe(v[["odsetek", "wskazanych_dni", "zlapane_wszystkie_proc", "trafienia_przy_alarmie_proc", "lift"]].rename(columns={
            "odsetek": "odsetek", "wskazanych_dni": "wskazanych dób", "zlapane_wszystkie_proc": "złapane dni z alarmem [%]",
            "trafienia_przy_alarmie_proc": "wskazań przy alarmie [%]", "lift": "lift (× częściej niż losowo)"}).round(2),
            width="stretch", hide_index=True)
        st.caption("Prawda = alarmy tłoczni Chorzów (±1 doba). Lift > 1: lepiej niż losowo.")
    else:
        st.caption("Tabela walidacji na alarmach CH pojawi się po `python main.py anomalie`.")
    try:
        from anomalie.ocena_anomalii import znane_zdarzenia
        zn = znane_zdarzenia(wsz)
        if len(zn):
            st.dataframe(zn.rename(columns={"zdarzenie": "znane zdarzenie", "obiekt": "pompownia", "dni": "dni",
                                            "wykryte_dni": "wykryte dni", "typy": "typy"}), width="stretch", hide_index=True)
            st.caption("Znane zdarzenia wg organizatorów: powódź IX 2024, przeciążenie RU_W I 2024.")
    except Exception:
        pass

    kolumny = [c for c in ["dzien", "kwh", "kwh_baza", "nadwyzka_kwh", "m3", "m3_baza", "nadwyzka_m3", "noc_udzial", "opad_doba",
                           "opad_3d", "temp_sr", "topnienie_cm", "residual_proc", "IF", "LOF", "SVM", "glosy", "anomalia", "typ",
                           "glowna_cecha", "opis"] if c in g]
    out = g[kolumny].assign(dzien=g["dzien"].dt.strftime("%Y-%m-%d")).round(3)
    Narzedzia.przycisk_pobierania("Dane dobowe (CSV)", Narzedzia.to_csv_bytes(out), f"anomalie_dobowo_{oid}.csv",
                                  "text/csv", key="as_csv")
