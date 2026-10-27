"""
Zakladka Prognoza - model gotowy do pracy (model/prognoza.py w projekcie): trening na wszystkich danych z bazy,
backtest na wgranym pliku (kazda doba prognozowana dzien wczesniej) i prognoza zuzycia energii na kolejne 24 h.
Plik: licznik narastajacy (jak mock_*), raport dystrybutora (Rap_godzinowy) albo prosty czas;kwh - rozpoznawany sam.
"""

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.wykresy import Wykresy


def _model_info(P):
    try:
        _, meta = P.wczytaj_model()
        st.success(f"Model {meta['wariant']}: {meta['drzew']} drzew, wytrenowany {meta['wytrenowano'][:16].replace('T', ' ')} "
                   f"na {meta['godzin']:,} godzinach ({', '.join(meta['obiekty'])}). "
                   f"WAPE dobowe na walidacji: {meta['wape_doba_walidacja']}%.")
        return True
    except FileNotFoundError:
        st.warning("Brak wytrenowanego modelu - kliknij 'Wytrenuj model'.")
        return False


def renderuj():
    st.subheader("Prognoza - szczegoly techniczne")
    st.caption("Widok dla klienta jest w zakladce 'Prognoza'. Tutaj: trening modelu, opcje, backtest i porownanie z regulami.")
    import model.prognoza as P

    d = st.session_state.get("d_baza")
    if d is None:
        st.info("Kliknij 'Wczytaj z bazy' w panelu bocznym - prognoza korzysta z historii, pogody i kalendarza z bazy.")
        return

    jest_model = _model_info(P)
    if st.button("Wytrenuj model (wszystkie dane z bazy)", type="secondary" if jest_model else "primary"):
        with st.spinner("Trening XGBoost na wszystkich danych (1-2 min)..."):
            try:
                P.trenuj(d)
                st.rerun()
            except Exception as e:
                st.error(f"Blad treningu: {e}")
    if not jest_model:
        return

    st.markdown("#### Dane do prognozy")
    obiekty_bazy = sorted(d["energia"]["obiekt_id"].unique())
    zrodlo = st.radio("Zrodlo", ["Obiekt z bazy", "Plik CSV (dane finalne)"], key="prog_zrodlo", horizontal=True)
    nowe = None
    if zrodlo == "Obiekt z bazy":
        oid = st.selectbox("Pompownia", obiekty_bazy, key="prog_obiekt")
        stacja = None
    else:
        plik = st.file_uploader("Plik CSV", type=["csv", "txt"], key="prog_plik",
                                help="Licznik narastajacy (data;godzina;typ;wartosc;status), raport dystrybutora "
                                     "(Rap_godzinowy) albo czas;kwh. Format rozpoznawany automatycznie.")
        c1, c2, c3 = st.columns(3)
        with c1:
            oid = st.text_input("Nazwa obiektu", value="RY_PZ1", key="prog_nazwa",
                                help="Nazwa z bazy (np. RY_PZ1) = dociagnieta wczesniejsza historia z bazy.")
        with c2:
            stacja = st.selectbox("Punkt pogody", ["RY", "RU", "CH"], key="prog_stacja")
        with c3:
            koniec = st.checkbox("Format czas;kwh: czas = koniec godziny", key="prog_koniec")
        if plik is None:
            return
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(plik.name).suffix) as t:
            t.write(plik.getvalue())
        try:
            nowe, rodzaj = P.wczytaj_plik(t.name, koniec)
            st.caption(f"Rozpoznany format: **{rodzaj}**, {len(nowe):,} godzin, "
                       f"{nowe['czas'].min().tz_convert('Europe/Warsaw'):%Y-%m-%d} → "
                       f"{nowe['czas'].max().tz_convert('Europe/Warsaw'):%Y-%m-%d}, suma {nowe['kwh'].sum():,.0f} kWh")
        except Exception as e:
            st.error(f"Nie udalo sie wczytac pliku: {e}")
            return

    pogoda_teraz = st.checkbox("Pobierz biezaca prognoze pogody (internet) - potrzebna do prognozy na jutro", value=True)
    uczciwie = st.checkbox("Uczciwy backtest - model trenowany od nowa BEZ okresu z pliku (1-2 min)", value=False,
                           disabled=nowe is None, key="prog_uczciwie",
                           help="Zapisany model widzial w treningu wszystkie dane z bazy. Jesli plik obejmuje okres juz "
                                "obecny w bazie, backtest bylby zawyzony - ta opcja to wyklucza.")
    if st.button("Prognozuj", type="primary"):
        with st.spinner("Licze cechy i prognoze..."):
            try:
                st.session_state.prog_wynik = (oid,) + P.uruchom(oid, nowe, d=d, stacja=stacja, pobierz_pogode=pogoda_teraz,
                                                                 uczciwie=uczciwie)
                ob = d["obiekty"].set_index("obiekt_id")
                st.session_state.prog_opis = dict(zrodlo=plik.name if nowe is not None else "baza danych",
                                                  stacja=stacja or (ob.loc[oid, "stacja_pogody"] if oid in ob.index else "RY"))
            except Exception as e:
                st.error(f"Blad prognozy: {e}")

    if st.session_state.get("prog_wynik") is None:
        return
    oid, wynik, met, mies, jutro = st.session_state.prog_wynik
    st.divider()
    st.markdown(f"#### {oid} - prognoza na {jutro['czas_lokalny'].min():%d.%m %H:%M} → {jutro['czas_lokalny'].max():%d.%m %H:%M}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prognoza 24 h", f"{jutro['prognoza'].sum():,.0f} kWh")
    if met:
        c2.metric("WAPE dobowe (backtest)", f"{met['WAPE_doba']}%")
        c3.metric("WAPE godzinowe", f"{met['WAPE_h']}%")
        c4.metric("Bias", f"{met['bias_proc']:+}%")
        st.caption(f"Backtest {met['od'][:10]} → {met['do'][:10]}{' (uczciwy - model bez okresu z pliku)' if met['uczciwie'] else ''}: "
                   f"kazda doba prognozowana dzien wczesniej, tylko z danych znanych w chwili prognozy. "
                   f"WAPE = suma |bledow| / suma zuzycia.")
        p = met.get("porownanie_WAPE_doba", {})
        if len(p) > 1:
            opisy = {"model": "model", **P.PROSTE_REGULY}
            st.dataframe(pd.DataFrame([dict(prognoza=opisy.get(k, k), WAPE_dobowe_proc=v,
                                            model_lepszy_o_proc=None if k == "model" else round(100 * (1 - p["model"] / v)))
                                       for k, v in p.items()]), width="stretch", hide_index=True)
        if met.get("widziane_w_treningu_proc", 0) > 0:
            st.warning(f"{met['widziane_w_treningu_proc']}% godzin z pliku model widzial w treningu - backtest jest zawyzony. "
                       f"Zaznacz 'Uczciwy backtest'.")
    elif nowe is None:
        st.caption("Bez pliku backtestu nie liczymy - model widzial dane z bazy w treningu.")
    Wykresy.show(Wykresy.fig_prognoza_24h(wynik, jutro))
    if met:
        Wykresy.show(Wykresy.fig_prognoza_dobowa(wynik))
        st.markdown("#### Sumy miesieczne")
        st.dataframe(mies, width="stretch")
    st.markdown("#### Prognoza godzinowa na 24 h")
    st.dataframe(jutro.assign(godzina=jutro["czas_lokalny"].dt.strftime("%d.%m %H:%M"))[["godzina", "prognoza"]].round(2),
                 width="stretch", hide_index=True)
    out = wynik.assign(czas=wynik["czas"].astype(str), czas_lokalny=wynik["czas_lokalny"].astype(str))
    Narzedzia.przycisk_pobierania("Pobierz prognoze (CSV)", Narzedzia.to_csv_bytes(out), f"{oid}_prognoza.csv",
                                  "text/csv", key="pob_prognoza")
