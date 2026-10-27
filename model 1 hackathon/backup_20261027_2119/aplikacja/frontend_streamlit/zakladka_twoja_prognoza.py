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
              help="Suma prognozowanego zuzycia energii w kolejnych 24 godzinach.")
    c2.metric("Najwięcej energii", f"godz. {s['szczyt_godz']}", pl(f"{s['szczyt_kwh']:.1f} kWh w tej godzinie"), delta_color="off")
    if "wape" in s:
        c3.metric("Średni błąd prognozy", pl(f"{s['wape']:.1f}%"), f"≈ {s['blad_kwh']:.0f} kWh na dobę", delta_color="off",
                  help="O ile średnio myliliśmy się w całym dniu, gdy prognozę robiliśmy dzień wcześniej (dane z pliku).")
        if "wczoraj" in s:
            c4.metric("Dokładniej niż „jak wczoraj”", f"{s['lepiej_niz_wczoraj']:+.0f}%",
                      pl(f"metoda „jak wczoraj”: {s['wczoraj']:.1f}% błędu"), delta_color="off",
                      help="Porównanie z najprostszą metodą: jutro zużycie będzie takie jak dziś.")
    else:
        c3.metric("Najmniej energii", f"godz. {s['dolek_godz']}", pl(f"{s['dolek_kwh']:.1f} kWh"), delta_color="off")
    st.markdown(s["tekst"])

    Wykresy.show(Wykresy.fig_jutro_slupki(jutro), key=f"{klucz}_wykres_jutro")
    if len(dz):
        Wykresy.show(Wykresy.fig_trafnosc_dobowa(dz), key=f"{klucz}_wykres_trafnosc")
        with st.expander(f"Dzień po dniu ({len(dz)} dób)"):
            t = dz.rename(columns={"data": "dzień", "rzeczywiste_kwh": "zużycie rzeczywiste [kWh]",
                                   "prognoza_kwh": "prognoza [kWh]", "roznica_kwh": "różnica [kWh]",
                                   "roznica_proc": "różnica [%]"})
            st.dataframe(t.round(1), width="stretch", hide_index=True)
        if mies is not None and len(mies) > 1:
            with st.expander("Miesiąc po miesiącu"):
                st.dataframe(mies.rename(columns={"kwh": "zużycie rzeczywiste [kWh]", "prognoza": "prognoza [kWh]",
                                                  "roznica_proc": "różnica [%]"}).round(1), width="stretch")

    st.markdown("#### Pobierz wyniki")
    c1, c2, c3 = st.columns(3)
    with c1:
        Narzedzia.przycisk_pobierania("Raport w Excelu (z wykresami)", excel_z_sesji(oid, s, dz), f"raport_{oid}.xlsx",
                                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{klucz}_xlsx")
    st.caption("Raport w Excelu: podsumowanie, jutro godzina po godzinie, dzień po dniu, miesiące i pogoda – z wykresami; "
               "do tego tydzień, plan na 2 miesiące i raport AI, jeśli zostały policzone w tej sesji.")
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
    c1.metric("Okres danych", f"{lok.min():%d.%m} – {lok.max():%d.%m.%Y}")
    c2.metric("Pełnych dób", f"{len(doby)}")
    c3.metric("Zużycie razem", f"{h.sum():,.0f} kWh".replace(",", " "))
    c4.metric("Średnio na dobę", f"{doby.mean():,.0f} kWh".replace(",", " ") if len(doby) else "–")
    if len(doby):
        st.caption(f"Format: {dp['rodzaj']} · zużycie dobowe od {doby.min():.0f} do {doby.max():.0f} kWh · "
                   + ("dane kompletne" if braki == 0 else f"brakujących godzin: {braki} (model sobie z tym poradzi)"))


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
                        "błąd na pliku [%]": b_plik, "typowy błąd z testu [%]": None if b_test is None else round(b_test, 1)})
    st.dataframe(pd.DataFrame(wiersze), width="stretch", hide_index=True)
    st.caption("Każdy dzień liczony osobnym modelem na tyle dni naprzód, z prognozą pogody wydaną z takim wyprzedzeniem. "
               "Im dalej, tym mniej pewna prognoza deszczu, więc i zużycia. „Błąd na pliku” - sprawdzenie na dniach z pliku "
               "(dla dni +2…+7 modelem zapisanym, który mógł widzieć ten okres); „typowy błąd z testu” - uczciwa ocena "
               "(python main.py horyzont).")
    out = tydzien.assign(czas=tydzien["czas_lokalny"].dt.strftime("%Y-%m-%d %H:%M"))[["czas", "dzien_naprzod", "prognoza"]].round(3)
    Narzedzia.przycisk_pobierania(f"Prognoza na {k_max} dni (CSV)", Narzedzia.to_csv_bytes(out), "prognoza_tydzien.csv",
                                  "text/csv", key="tp_tydzien_csv")


def _plan(P, d, oid, nowe, stacja):
    import model.dlugi as D
    st.caption("Plan dobowy na 2 miesiące: kalendarz, pora roku, ostatni poziom pompowni i **typowa pogoda dla tej pory roku** "
               "(pogody na tygodnie naprzód nikt nie zna). Do budżetu i zakupu energii, nie do pojedynczych godzin.")
    try:
        D.wczytaj_model()
    except FileNotFoundError:
        st.warning("Brak modelu planu - wytrenuj go w zakładce **Model** albo `python main.py prognoza --trenuj --dni 7`.")
        return
    if st.button("Przygotuj plan na 2 miesiące", type="primary", key="tp_plan"):
        with st.spinner("Liczę plan..."):
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
        jak = (f" W teście średni błąd dobowy wyniósł {r1[kol]:.1f}% dla pierwszego tygodnia i {r4[kol]:.1f}% dla dni 31–60 "
               f"(„średnia z ostatnich 4 tygodni”: {r1['jak_ostatnie_4tyg']:.1f}% / {r4['jak_ostatnie_4tyg']:.1f}%); przedział objął "
               f"prawdziwą wartość w {r1['pokrycie_p10_p90']:.0f}% dni pierwszego tygodnia i {r4['pokrycie_p10_p90']:.0f}% dni 31–60.")
    jak += f" Metoda planu (wybrana na danych historycznych): {meta_planu.get('opis_metody', 'model ML')}."
    s4 = tyg[tyg["tydzien"] <= 4]
    st.markdown(f"Najbardziej prawdopodobne zużycie w najbliższych 4 tygodniach to **{t4['p50'].sum():,.0f} kWh** "
                f"(tygodniowo zwykle {s4['p10'].mean():,.0f}–{s4['p90'].mean():,.0f} kWh).".replace(",", " ") + jak)
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
    st.caption("Zakresy tygodni i miesięcy pochodzą z rzeczywistych błędów sum tej pompowni w przeszłości (ok. 80% sum "
               "mieści się w zakresie) - dni deszczowe i suche częściowo się znoszą, więc zakres sumy jest węższy niż suma dziennych granic.")
    out = dz.assign(dzien=dz["dzien"].dt.strftime("%Y-%m-%d")).round(1)
    c1, c2 = st.columns(2)
    with c1:
        Narzedzia.przycisk_pobierania("Plan w Excelu (z wykresami)", excel_z_sesji(oid), f"plan_2_miesiace_{oid}.xlsx",
                                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="tp_plan_xlsx")
    with c2:
        Narzedzia.przycisk_pobierania("Plan dzień po dniu (CSV)", Narzedzia.to_csv_bytes(out), f"plan_2_miesiace_{oid}.csv",
                                      "text/csv", key="tp_plan_csv")


def renderuj():
    st.subheader("Prognoza zużycia energii pompowni")
    import model.prognoza as P

    d = st.session_state.get("d_baza")
    if d is None:
        st.warning("Brak połączenia z bazą danych - uruchom bazę (`docker compose up -d db`) i odśwież stronę.")
        return
    dp = st.session_state.get("dane_prognozy")
    if dp is None:
        st.info("👈 Wgraj plik(i) z zużyciem energii w panelu po lewej i kliknij **Wczytaj pliki**. Dane obejrzysz w zakładce **Dane**, "
                "a tutaj jednym przyciskiem przygotujesz **prognozę na kolejną dobę** i sprawdzisz, **jak dokładne byłyby "
                "nasze prognozy** w okresie z pliku.")
        return
    try:
        _, meta = P.wczytaj_model()
    except FileNotFoundError:
        st.info("Model nie jest jeszcze przygotowany - przygotuję go raz na wszystkich danych (1-2 min).")
        if st.button("Przygotuj model", type="primary", key="tp_trenuj"):
            with st.spinner("Uczę model na wszystkich danych..."):
                P.trenuj(d)
            st.rerun()
        return

    oid, nowe, stacja = dp["oid"], dp["nowe"], dp["stacja"]
    st.markdown(f"Dane: **{dp['zrodlo']}** · pompownia **{oid}**" + (" (nowa, spoza bazy)" if stacja else "")
                + " · zmienisz je w panelu po lewej.")
    _podsumowanie_danych(nowe, dp)
    opis = dict(zrodlo=dp["zrodlo"], stacja=stacja)
    if opis["stacja"] is None:
        ob = d["obiekty"].set_index("obiekt_id")
        opis["stacja"] = ob.loc[oid, "stacja_pogody"] if oid in ob.index else "RY"

    horyzont = st.radio("Na ile do przodu", ["Jutro (24 h)", "Tydzień (7 dni)", "2 miesiące (plan)"], horizontal=True,
                        key="tp_horyzont", help="Jutro: najdokładniejsza, z prognozą pogody. Tydzień: każdy dzień osobnym modelem, "
                                                "z prognozą pogody wydaną tyle dni wcześniej. 2 miesiące: plan dobowy z przedziałem, "
                                                "bez prognozy pogody (typowa pogoda dla pory roku) - do budżetu i zakupu energii.")
    if horyzont.startswith("Tydzień") and P.dostepne_dni() < 2:
        st.warning("Brak modeli na kilka dni naprzód - wytrenuj je w zakładce **Model** (przycisk „Wytrenuj modele 1–7 dni "
                   "i plan 2 miesiące”) albo `python main.py prognoza --trenuj --dni 7`.")
        return
    if horyzont.startswith("2 miesiące"):
        _plan(P, d, oid, nowe, stacja)
        return

    widziane = P.widziane_w_treningu(meta, oid, nowe)
    if widziane > 0:
        st.info(f"Plik obejmuje okres, na którym model się uczył ({100 * widziane:.0f}% godzin). Żeby sprawdzenie było "
                f"uczciwe, przed prognozą nauczymy model od nowa **bez tego okresu** - potrwa to 1-2 minuty.")
    with st.expander("Ustawienia zaawansowane"):
        pogoda = st.checkbox("Pobierz aktualną prognozę pogody z internetu", value=True, key="tp_pogoda")
        uczciwie = st.checkbox("Ucz model bez okresu z pliku (uczciwe sprawdzenie)", value=widziane > 0, key="tp_uczciwie",
                               disabled=nowe is None)

    if st.button("Przygotuj prognozę", type="primary", key="tp_start"):
        with st.spinner("Liczę prognozę..." + (" (najpierw uczę model bez okresu z pliku, 1-2 min)" if uczciwie and nowe is not None else "")):
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
                st.error(f"Coś poszło nie tak: {e}")

    prog = st.session_state.get("prog_wynik")
    if prog is not None and prog[0] == oid:
        st.divider()
        tydz = st.session_state.get("prog_tydzien")
        if horyzont.startswith("Tydzień") and tydz is not None and tydz[0] == oid:
            _tydzien(tydz[1], tydz[2])
            st.divider()
            st.markdown("#### Szczegóły pierwszej doby")
        pokaz_podsumowanie(prog, st.session_state.get("prog_opis", {}), d)
        with st.expander("Jak to liczymy?"):
            st.markdown("""
- Model uczy się na historii zużycia energii pompowni, kalendarzu (dni wolne, święta, ferie) i pogodzie,
  w tym **prognozie pogody wydanej dzień wcześniej** - tak, jak byłoby naprawdę.
- **Sprawdzenie na danych z pliku:** dla każdego dnia liczymy prognozę tylko z informacji znanych dzień wcześniej
  i porównujemy z tym, ile pompownia zużyła naprawdę. **Średni błąd** to o ile średnio się myliliśmy, w procentach
  dziennego zużycia.
- Najtrudniejsze są **dni z ulewą** - woda deszczowa trafia do kanalizacji, a deszcz trudno dokładnie przewidzieć.
- Na podstawie czego powstała prognoza (pogoda, kalendarz, porównanie z prostymi metodami): zakładka
  *Prognoza – szczegóły*. Jak dobry jest model ogólnie: zakładka *Model*.
""")
