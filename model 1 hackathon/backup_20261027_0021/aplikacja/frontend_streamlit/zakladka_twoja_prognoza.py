"""
Zakladka Twoja prognoza - widok dla klienta, ktory nie zna sie na modelach: wgraj plik, jeden przycisk, wynik opisany
prostym jezykiem (liczony w Pythonie, bez LLM), wykresy i pliki do pobrania. Szczegoly techniczne sa w kolejnych zakladkach.
"""

import pandas as pd
import streamlit as st

from backend_ml_llm.podsumowanie_klienta import podsumuj, excel, pl
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.wykresy import Wykresy



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
        Narzedzia.przycisk_pobierania("Wszystko w Excelu (.xlsx)", excel(s, dz, jutro, mies, wynik), f"prognoza_{oid}.xlsx",
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


def renderuj():
    st.subheader("Prognoza zużycia energii pompowni")
    import model.prognoza as P

    d = st.session_state.get("d_baza")
    if d is None:
        st.warning("Brak połączenia z bazą danych - uruchom bazę (`docker compose up -d db`) i odśwież stronę.")
        return
    dp = st.session_state.get("dane_prognozy")
    if dp is None:
        st.info("👈 Wgraj plik z danymi (albo wybierz pompownię z bazy) w panelu po lewej. Dane obejrzysz w zakładce **Dane**, "
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
    opis = dict(zrodlo=dp["zrodlo"], stacja=stacja)
    if opis["stacja"] is None:
        ob = d["obiekty"].set_index("obiekt_id")
        opis["stacja"] = ob.loc[oid, "stacja_pogody"] if oid in ob.index else "RY"

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
                st.session_state.prog_wynik = (oid,) + P.uruchom(oid, nowe, d=d, stacja=stacja, pobierz_pogode=pogoda,
                                                                 uczciwie=bool(uczciwie and nowe is not None))
                st.session_state.prog_opis = opis
                st.session_state.prog_dd = getattr(P.uruchom, "ostatnie", None)     # dla zakladki „Prognoza – szczegoly”
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Coś poszło nie tak: {e}")

    prog = st.session_state.get("prog_wynik")
    if prog is not None and prog[0] == oid:
        st.divider()
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
