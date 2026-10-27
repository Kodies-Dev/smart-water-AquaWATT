"""
Zakladka Twoja prognoza - widok dla klienta, ktory nie zna sie na modelach: wgraj plik, jeden przycisk, wynik opisany
prostym jezykiem (liczony w Pythonie, bez LLM), wykresy i pliki do pobrania. Szczegoly techniczne sa w kolejnych zakladkach.
"""

import pandas as pd
import streamlit as st

from backend_ml_llm.podsumowanie_klienta import podsumuj, pl
from backend_ml_llm.raport_excel import raport_excel
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.wykresy import Wykresy



def _bledy_testu():
    return {k: b for k in range(1, 8) if (b := _blad_ogolny(k)) is not None}


def excel_z_sesji(oid, s=None, dz=None):
    """Raport Excel z wykresami ze wszystkiego, co policzono w tej sesji dla pompowni: jutro, tydzień, plan, pogoda, LLM."""
    ss = st.session_state
    prog = ss.get("prog_wynik") if ss.get("prog_wynik") is not None and ss["prog_wynik"][0] == oid else None
    tydz = ss.get("prog_tydzien") if ss.get("prog_tydzien") is not None and ss["prog_tydzien"][0] == oid else None
    plan = ss.get("prog_plan") if ss.get("prog_plan") is not None and ss["prog_plan"][0] == oid else None
    wej = None
    if prog is not None and ss.get("prog_dd") is not None:
        from frontend_streamlit.zakladka_prognoza_szczegoly import dane_wejsciowe
        try:
            wej = dane_wejsciowe(prog[1], ss["prog_dd"])
        except Exception:
            wej = None
    fakty = None
    if ss.get("raport_prognozy"):
        from backend_ml_llm.raport_prognozy import fakty as policz_fakty, wczytaj_wyniki
        meta, met, _, _ = wczytaj_wyniki()
        fakty = policz_fakty(meta, met, prog)
    _, wynik, met, mies, jutro = prog if prog is not None else (None, None, None, None, None)
    return raport_excel(oid, ss.get("prog_opis", {}).get("zrodlo", ""), s, dz, jutro, mies, wynik, met,
                        tydz[1] if tydz else None, tydz[2] if tydz else None, _bledy_testu(),
                        plan[1:] if plan else None, wej, ss.get("raport_prognozy"), fakty)


def pokaz_podsumowanie(prog, opis, d, klucz="tp"):
    """Wynik dla klienta: kafelki, opis, wykresy, tabela, pobieranie. Uzywane tez w zakladce Raport."""
    s, dz = podsumuj(prog, opis, d)
    oid, wynik, met, mies, jutro = prog
    st.markdown(f"### Wynik dla pompowni {oid}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Prognoza na {s['jutro_od']:%d.%m.%Y}", f"{s['jutro_kwh']:,.0f} kWh".replace(",", " "),
              help="Suma na kolejne 24 h.")
    c2.metric("Szczyt", f"godz. {s['szczyt_godz']}", pl(f"{s['szczyt_kwh']:.1f} kWh w tej godzinie"), delta_color="off")
    if "wape" in s:
        c3.metric("Błąd (WAPE)", pl(f"{s['wape']:.1f}%"), f"≈ {s['blad_kwh']:.0f} kWh na dobę", delta_color="off",
                  help="Średni błąd dobowy prognozy D-1 na danych z pliku.")
        if "wczoraj" in s:
            c4.metric("Poprawa vs „jak wczoraj”", f"{s['lepiej_niz_wczoraj']:+.0f}%",
                      pl(f"„jak wczoraj”: {s['wczoraj']:.1f}%"), delta_color="off",
                      help="Metoda naiwna: jutro = dziś.")
    else:
        c3.metric("Minimum", f"godz. {s['dolek_godz']}", pl(f"{s['dolek_kwh']:.1f} kWh"), delta_color="off")
    st.markdown(s["tekst"])

    Wykresy.show(Wykresy.fig_jutro_slupki(jutro), key=f"{klucz}_wykres_jutro")
    if len(dz):
        Wykresy.show(Wykresy.fig_trafnosc_dobowa(dz), key=f"{klucz}_wykres_trafnosc")
        with st.expander(f"Dzień po dniu ({len(dz)} dób)"):
            t = dz.rename(columns={"data": "dzień", "rzeczywiste_kwh": "rzeczywiste [kWh]",
                                   "prognoza_kwh": "prognoza [kWh]", "roznica_kwh": "różnica [kWh]",
                                   "roznica_proc": "różnica [%]"})
            st.dataframe(t.round(1), width="stretch", hide_index=True)
        if mies is not None and len(mies) > 1:
            with st.expander("Miesiąc po miesiącu"):
                st.dataframe(mies.rename(columns={"kwh": "rzeczywiste [kWh]", "prognoza": "prognoza [kWh]",
                                                  "roznica_proc": "różnica [%]"}).round(1), width="stretch")

    st.markdown("#### Eksport")
    c1, c2, c3 = st.columns(3)
    with c1:
        Narzedzia.przycisk_pobierania("Raport Excel", excel_z_sesji(oid, s, dz), f"raport_{oid}.xlsx",
                                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{klucz}_xlsx")
    with c2:
        j = pd.DataFrame({"godzina": jutro["czas_lokalny"].dt.strftime("%Y-%m-%d %H:%M"), "prognoza_kwh": jutro["prognoza"].round(2)})
        Narzedzia.przycisk_pobierania("Prognoza na 24 h (CSV)", Narzedzia.to_csv_bytes(j), f"prognoza_24h_{oid}.csv",
                                      "text/csv", key=f"{klucz}_jutro")
    with c3:
        if len(dz):
            Narzedzia.przycisk_pobierania("Dzień po dniu (CSV)", Narzedzia.to_csv_bytes(dz.round(2)), f"dzien_po_dniu_{oid}.csv",
                                          "text/csv", key=f"{klucz}_dz")
    return s


def _podsumowanie_danych(nowe, dp):
    """Kafelki o danych do prognozy (bez strzalek) + jedna linia szczegolow."""
    h = nowe.set_index("czas")["kwh"]
    lok = h.index.tz_convert("Europe/Warsaw")
    doby = h.groupby(lok.date).agg(["sum", "count"])
    doby = doby[doby["count"] >= 23]["sum"]
    braki = int(pd.date_range(h.index.min(), h.index.max(), freq="h").difference(h.index).size)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Okres", f"{lok.min():%d.%m} – {lok.max():%d.%m.%Y}")
    c2.metric("Pełnych dób", f"{len(doby)}")
    c3.metric("Suma", f"{h.sum():,.0f} kWh".replace(",", " "))
    c4.metric("Średnio na dobę", f"{doby.mean():,.0f} kWh".replace(",", " ") if len(doby) else "–")
    if len(doby):
        st.caption(f"Format: {dp['rodzaj']} · doby {doby.min():.0f}–{doby.max():.0f} kWh · "
                   + ("bez braków" if braki == 0 else f"braki: {braki} h"))


def _blad_ogolny(k):
    """Średni błąd dobowy na teście dla prognozy k dni naprzód (wyniki/horyzont.csv), jeśli policzony."""
    from model.config import WYNIKI
    p = WYNIKI / "horyzont.csv"
    if not p.exists():
        return None
    t = pd.read_csv(p)
    r = t[(t["obiekt"] == "RAZEM") & (t["dni"] == k)]
    return float(r["model"].iloc[0]) if len(r) else None


def _tydzien(tydzien, bledy):
    k_max = int(tydzien["dzien_naprzod"].max())
    st.markdown(f"### Prognoza na {k_max} dni")
    g = tydzien.groupby("dzien_naprzod").agg(od=("czas_lokalny", "min"), do=("czas_lokalny", "max"), kwh=("prognoza", "sum"),
                                              szczyt=("prognoza", "max"))
    c = st.columns(min(4, k_max))
    c[0].metric(f"Razem {k_max} dni", f"{g['kwh'].sum():,.0f} kWh".replace(",", " "))
    c[1 % len(c)].metric("Średnio na dobę", f"{g['kwh'].mean():,.0f} kWh".replace(",", " "))
    Wykresy.show(Wykresy.fig_tydzien(tydzien), key="tp_tydzien")
    wiersze = []
    for k, r in g.iterrows():
        b_plik, b_test = bledy.get(k), _blad_ogolny(k)
        wiersze.append({"dzień naprzód": f"+{k}", "od": f"{r['od']:%d.%m %H:%M}", "do": f"{r['do']:%d.%m %H:%M}",
                        "prognoza [kWh]": round(r["kwh"], 1), "szczyt [kWh/h]": round(r["szczyt"], 1),
                        "błąd – plik [%]": b_plik, "błąd – test [%]": None if b_test is None else round(b_test, 1)})
    st.dataframe(pd.DataFrame(wiersze), width="stretch", hide_index=True)
    st.caption("Dzień +K: osobny model, prognoza pogody wydana K dni wcześniej. Błąd – plik: na dniach z pliku; "
               "błąd – test: uczciwa ocena na teście.")
    out = tydzien.assign(czas=tydzien["czas_lokalny"].dt.strftime("%Y-%m-%d %H:%M"))[["czas", "dzien_naprzod", "prognoza"]].round(3)
    Narzedzia.przycisk_pobierania(f"Prognoza na {k_max} dni (CSV)", Narzedzia.to_csv_bytes(out), "prognoza_tydzien.csv",
                                  "text/csv", key="tp_tydzien_csv")


def _plan(P, d, oid, nowe, stacja):
    import model.dlugi as D
    st.caption("Plan dobowy: kalendarz, sezon, poziom pompowni i typowa pogoda. Do budżetu i zakupu energii.")
    try:
        D.wczytaj_model()
    except FileNotFoundError:
        st.warning("Brak modelu planu. Wytrenuj go w zakładce **Model**.")
        return
    if st.button("Przygotuj plan na 2 miesiące", type="primary", key="tp_plan"):
        with st.spinner("Obliczanie planu..."):
            try:
                st.session_state.prog_plan = (oid,) + D.prognoza(d, oid, nowe, stacja)
            except ValueError as e:
                st.error(str(e))
    plan = st.session_state.get("prog_plan")
    if plan is None or plan[0] != oid:
        return
    _, dz, tyg, mies, start = plan
    st.divider()
    st.markdown(f"### Plan dla pompowni {oid} – od {dz['dzien'].min():%d.%m.%Y} do {dz['dzien'].max():%d.%m.%Y}")
    c1, c2, c3 = st.columns(3)
    t4 = dz[dz["dni"] <= 28]
    c1.metric("Najbliższe 4 tygodnie", f"{t4['p50'].sum():,.0f} kWh".replace(",", " "))
    c2.metric("Cały okres (60 dni)", f"{dz['p50'].sum():,.0f} kWh".replace(",", " "))
    c3.metric("Średnio na dobę", f"{dz['p50'].mean():,.0f} kWh".replace(",", " "))
    from model.config import WYNIKI
    jak = ""
    _, meta_planu = D.wczytaj_model()
    if (WYNIKI / "dlugi.csv").exists():
        q = pd.read_csv(WYNIKI / "dlugi.csv").set_index("dni")
        kol = "plan" if "plan" in q else "model_p50"
        r1, r4 = q.iloc[0], q.iloc[-1]
        jak = (f"Test: błąd dobowy {r1[kol]:.1f}% (tydzień 1) / {r4[kol]:.1f}% (dni 31–60), „średnia 4 tyg.” "
               f"{r1['jak_ostatnie_4tyg']:.1f}% / {r4['jak_ostatnie_4tyg']:.1f}%; pokrycie przedziału "
               f"{r1['pokrycie_p10_p90']:.0f}% / {r4['pokrycie_p10_p90']:.0f}%.")
    jak += f" Metoda: {meta_planu.get('opis_metody', 'model ML')}."
    s4 = tyg[tyg["tydzien"] <= 4]
    st.markdown(f"Najbliższe 4 tygodnie: **{t4['p50'].sum():,.0f} kWh** "
                f"(tygodniowo zwykle {s4['p10'].mean():,.0f}–{s4['p90'].mean():,.0f} kWh).".replace(",", " "))
    st.caption(jak.strip())
    Wykresy.show(Wykresy.fig_plan(dz), key="tp_plan_wykres")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Tydzień po tygodniu")
        st.dataframe(tyg.assign(od=tyg["od"].dt.strftime("%d.%m"), do=tyg["do"].dt.strftime("%d.%m")).rename(
            columns={"tydzien": "tydzień", "p50": "prognoza [kWh]", "p10": "od [kWh]", "p90": "do [kWh]"}).round(0),
            width="stretch", hide_index=True)
    with c2:
        st.markdown("#### Miesiąc po miesiącu")
        st.dataframe(mies.rename(columns={"miesiac": "miesiąc", "p50": "prognoza [kWh]", "p10": "od [kWh]", "p90": "do [kWh]"}).round(0),
                     width="stretch", hide_index=True)
    st.caption("Zakresy z historycznych błędów sum tej pompowni (ok. 80% sum w zakresie).")
    out = dz.assign(dzien=dz["dzien"].dt.strftime("%Y-%m-%d")).round(1)
    c1, c2 = st.columns(2)
    with c1:
        Narzedzia.przycisk_pobierania("Plan – Excel", excel_z_sesji(oid), f"plan_2_miesiace_{oid}.xlsx",
                                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="tp_plan_xlsx")
    with c2:
        Narzedzia.przycisk_pobierania("Plan – CSV", Narzedzia.to_csv_bytes(out), f"plan_2_miesiace_{oid}.csv",
                                      "text/csv", key="tp_plan_csv")


def renderuj():
    st.subheader("Prognoza zużycia energii")
    import model.prognoza as P

    d = st.session_state.get("d_baza")
    if d is None:
        st.warning("Dane referencyjne (pogoda, kalendarz) nie zostały załadowane. Odśwież stronę.")
        return
    dp = st.session_state.get("dane_prognozy")
    if dp is None:
        st.info("Wgraj plik CSV z zużyciem energii w panelu bocznym i kliknij **Wczytaj pliki**.")
        return
    try:
        _, meta = P.wczytaj_model()
    except FileNotFoundError:
        st.info("Brak wytrenowanego modelu. Przygotowanie modelu jednorazowo zajmuje 1–2 min.")
        if st.button("Przygotuj model", type="primary", key="tp_trenuj"):
            with st.spinner("Uczę model na wszystkich danych..."):
                P.trenuj(d)
            st.rerun()
        return

    oid, nowe, stacja = dp["oid"], dp["nowe"], dp["stacja"]
    st.markdown(f"**{dp['zrodlo']}** · pompownia **{oid}**" + (" (nowa)" if stacja else ""))
    _podsumowanie_danych(nowe, dp)
    opis = dict(zrodlo=dp["zrodlo"], stacja=stacja)
    if opis["stacja"] is None:
        ob = d["obiekty"].set_index("obiekt_id")
        opis["stacja"] = ob.loc[oid, "stacja_pogody"] if oid in ob.index else "RY"

    horyzont = st.radio("Horyzont", ["Jutro (24 h)", "Tydzień (7 dni)", "2 miesiące (plan)"], horizontal=True,
                        key="tp_horyzont", help="Jutro: z prognozą pogody. Tydzień: osobny model na każdy dzień. "
                                                "2 miesiące: plan dobowy z przedziałem (typowa pogoda).")
    if horyzont.startswith("Tydzień") and P.dostepne_dni() < 2:
        st.warning("Brak modeli na kilka dni naprzód. Wytrenuj je w zakładce **Model**.")
        return
    if horyzont.startswith("2 miesiące"):
        _plan(P, d, oid, nowe, stacja)
        return

    widziane = P.widziane_w_treningu(meta, oid, nowe)
    if widziane > 0:
        st.info(f"{100 * widziane:.0f}% godzin z pliku znajduje się w danych treningowych. Dla rzetelnej oceny model zostanie wytrenowany ponownie bez tego okresu (1–2 min).")
    pogoda = True                                                   # pogoda zawsze z Open-Meteo
    with st.expander("Ustawienia zaawansowane"):
        uczciwie = st.checkbox("Uczciwy backtest (model bez okresu z pliku)", value=widziane > 0, key="tp_uczciwie",
                               disabled=nowe is None)

    if st.button("Przygotuj prognozę", type="primary", key="tp_start"):
        with st.spinner("Obliczanie prognozy..." + (" (trening modelu bez okresu z pliku, 1–2 min)" if uczciwie and nowe is not None else "")):
            try:
                if horyzont.startswith("Tydzień"):
                    w, m, mi, j, tydz, bl = P.uruchom_dni(oid, nowe, d=d, stacja=stacja, pobierz_pogode=pogoda,
                                                          uczciwie=bool(uczciwie and nowe is not None), dni=7)
                    st.session_state.prog_wynik = (oid, w, m, mi, j)
                    st.session_state.prog_tydzien = (oid, tydz, bl)
                else:
                    st.session_state.prog_wynik = (oid,) + P.uruchom(oid, nowe, d=d, stacja=stacja, pobierz_pogode=pogoda,
                                                                     uczciwie=bool(uczciwie and nowe is not None))
                    st.session_state.prog_tydzien = None
                st.session_state.prog_opis = opis
                st.session_state.prog_dd = getattr(P.uruchom, "ostatnie", None)     # dla zakladki „Prognoza – szczegoly”
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Błąd obliczeń: {e}")

    prog = st.session_state.get("prog_wynik")
    if prog is not None and prog[0] == oid:
        st.divider()
        tydz = st.session_state.get("prog_tydzien")
        if horyzont.startswith("Tydzień") and tydz is not None and tydz[0] == oid:
            _tydzien(tydz[1], tydz[2])
            st.divider()
            st.markdown("#### Pierwsza doba")
        pokaz_podsumowanie(prog, st.session_state.get("prog_opis", {}), d)
        with st.expander("Metodyka"):
            st.markdown("""
- **Model:** XGBoost na historii zużycia, kalendarzu i pogodzie, w tym prognozie pogody wydanej dzień wcześniej (D-1).
- **Backtest:** każda doba z pliku prognozowana tylko z danych znanych dzień wcześniej. WAPE = średni błąd dobowy.
- **Największy błąd:** doby z intensywnym opadem (trafność prognozy opadu).
- Dane wejściowe i porównanie z prostymi metodami: **Szczegóły prognozy**. Ogólna jakość: zakładka **Model**.
""")
