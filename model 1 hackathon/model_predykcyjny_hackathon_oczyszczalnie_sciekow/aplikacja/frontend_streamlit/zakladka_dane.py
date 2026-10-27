"""
Zakładka Dane - podgląd wczytanego zbioru, porównanie kilku zbiorów naraz,
łączenie tabel (union / join jak w SQL), tabela przestawna i zapytania SQL.

To najbardziej rozbudowana zakładka w całej aplikacji, bo tu dzieje się
całe przygotowanie danych zanim cokolwiek trafi do detekcji anomalii.
"""

import pandas as pd
import streamlit as st

try:
    import duckdb  # zapytania SQL na wczytanych zbiorach
except ImportError:
    duckdb = None

from frontend_streamlit.magazyn_danych import MagazynDanych
from frontend_streamlit.narzedzia import Narzedzia
from frontend_streamlit.pola import Pola
from frontend_streamlit.wykresy import Wykresy


def _sekcja_podglad(raw_df, all_num_cols):
    st.subheader(f"Zbiór: {st.session_state.aktywny}")
    st.dataframe(raw_df.head(200), width="stretch")

    c1, c2, c3 = st.columns(3)  # dzieli pole na 3 rowne kolumny
    c1.metric("Wiersze", len(raw_df))  # duze kafelki - metryki
    c2.metric("Kolumny", len(raw_df.columns))
    c3.metric("Kolumny numeryczne", len(all_num_cols))

    if all_num_cols:
        st.subheader("Statystyki opisowe")  # mniejszy naglowek
        st.dataframe(raw_df[all_num_cols].describe().T, width="stretch")  # transponuje describe,
        # nazwy sa wierszami zamiast kolumnami
    else:
        st.warning("Zbiór nie ma kolumn numerycznych - detekcja anomalii będzie niemożliwa.")

    braki = raw_df.isnull().sum()
    braki = braki[braki > 0]
    if len(braki) > 0:
        st.subheader("Braki danych")
        st.dataframe(braki.rename("liczba braków"), width="stretch")
    else:
        st.success("Brak pustych wartości w danych.")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        Narzedzia.przycisk_pobierania(
            "Pobierz ten zbiór (CSV)", Narzedzia.to_csv_bytes(raw_df),
            f"{st.session_state.aktywny}.csv", "text/csv", key="pob_zbior")
    with c2:
        if st.button("Usuń ten zbiór z pamięci"):
            MagazynDanych.usun(st.session_state.aktywny)
            st.rerun()


def _sekcja_porownanie():
    st.subheader("Porównanie wczytanych zbiorów")

    if len(st.session_state.zbiory) < 2:
        st.info("Wgraj przynajmniej dwa pliki, żeby było co porównywać.")
        return

    wiersze = []
    for nazwa, d in st.session_state.zbiory.items():
        num = d.select_dtypes(include="number")
        wiersze.append({
            "Zbior": nazwa,
            "Wierszy": len(d),
            "Kolumn": len(d.columns),
            "Kolumn liczbowych": len(num.columns),
            "Braków danych": int(d.isnull().sum().sum()),
        })
    st.dataframe(pd.DataFrame(wiersze), width="stretch", hide_index=True)

    st.markdown("#### Zgodność kolumn")
    nazwy = list(st.session_state.zbiory.keys())
    wspolne = set(st.session_state.zbiory[nazwy[0]].columns)
    for n in nazwy[1:]:
        wspolne &= set(st.session_state.zbiory[n].columns)

    if wspolne:
        st.success(f"Kolumny wspólne dla wszystkich zbiorów ({len(wspolne)}): "
                   + ", ".join(sorted(map(str, wspolne))))
    else:
        st.warning("Zbiory nie mają ani jednej wspólnej kolumny.")

    for nazwa, d in st.session_state.zbiory.items():
        tylko_tu = set(d.columns) - wspolne
        if tylko_tu:
            st.caption(f"{nazwa} - kolumny występujące tylko tutaj: "
                       + ", ".join(sorted(map(str, tylko_tu))))

    st.markdown("#### Porównanie statystyk wybranej kolumny")
    kol_wspolne_num = sorted([c for c in wspolne
                              if all(pd.api.types.is_numeric_dtype(d[c])
                                     for d in st.session_state.zbiory.values())])
    if not kol_wspolne_num:
        st.info("Brak wspólnych kolumn liczbowych do porównania.")
        return

    kol = st.selectbox("Kolumna liczbowa", kol_wspolne_num, key="por_kol")
    por = []
    for nazwa, d in st.session_state.zbiory.items():
        s = d[kol].dropna()
        por.append({"Zbior": nazwa, "Liczba": len(s),
                    "Srednia": round(s.mean(), 3) if len(s) else None,
                    "Mediana": round(s.median(), 3) if len(s) else None,
                    "Odch. std": round(s.std(), 3) if len(s) else None,
                    "Min": round(s.min(), 3) if len(s) else None,
                    "Max": round(s.max(), 3) if len(s) else None})
    st.dataframe(pd.DataFrame(por), width="stretch", hide_index=True)

    import plotly.graph_objects as go
    fig = go.Figure()
    for nazwa, d in st.session_state.zbiory.items():
        fig.add_trace(go.Box(y=d[kol].dropna(), name=nazwa))
    Wykresy.show(Wykresy.style_fig(fig, f"Rozkład kolumny {kol} w poszczególnych zbiorach",
                                   None, kol, None))


def _sekcja_laczenie():
    st.subheader("Łączenie tabel")

    if len(st.session_state.zbiory) < 2:
        st.info("Potrzebne sa przynajmniej dwa zbiory.")
        return

    tryb = st.radio(
        "Sposób łączenia",
        ["Doklejanie wierszy (te same kolumny)", "Złączenie po kluczu (join)"],
        key="tryb_lacz",
    )
    nazwy = list(st.session_state.zbiory.keys())

    # --- union ---
    if tryb.startswith("Doklejanie"):
        st.caption("Wiersze kolejnych zbiorów trafiają jeden pod drugi. "
                   "Odpowiednik UNION ALL w SQL.")
        wybrane = st.multiselect("Zbiory do połączenia", nazwy, default=nazwy[:2],
                                 key="union_zbiory")
        dodaj_kol = st.checkbox("Dodaj kolumnę z nazwa zbioru źródłowego", value=True,
                                help="Przydatne, gdy później chcesz rozróżnić pochodzenie wiersza "
                                     "albo użyć jej jako kolumny jednostki w trybie panelowym.")

        nazwa_union = st.text_input("Nazwa nowego zbioru", "polaczone", key="union_nazwa",
                                    help="Pod ta nazwa wynik pojawi się na liście zbiorów "
                                         "i jako tabela w zakładce SQL.")

        if len(wybrane) >= 2:
            zestawy = [set(st.session_state.zbiory[n].columns) for n in wybrane]
            wspolne = set.intersection(*zestawy)
            roznice = set.union(*zestawy) - wspolne
            if roznice:
                st.warning("Zbiory różnią się kolumnami. Niepasujące kolumny będą "
                           "wypełnione pustymi wartościami: " + ", ".join(sorted(map(str, roznice))))

            if st.button("Polacz", type="primary", key="btn_union"):
                czesci = []
                for n in wybrane:
                    d = st.session_state.zbiory[n].copy()
                    if dodaj_kol:
                        d["_zbior"] = n
                    czesci.append(d)
                wynik = pd.concat(czesci, ignore_index=True)
                nowa = MagazynDanych.dodaj(nazwa_union or "polaczone", wynik)
                st.success(f"Utworzono zbiór '{nowa}' - {len(wynik)} wierszy.")
                st.rerun()

    # --- join ---
    else:
        st.caption("Odpowiednik JOIN w SQL - wiersze łączone sa po wspólnym kluczu.")
        c1, c2 = st.columns(2)
        with c1:
            lewa = st.selectbox("Tabela lewa", nazwy, key="join_lewa")
        with c2:
            prawa = st.selectbox("Tabela prawa", nazwy,
                                 index=1 if len(nazwy) > 1 else 0, key="join_prawa")

        dl, dp = st.session_state.zbiory[lewa], st.session_state.zbiory[prawa]
        c1, c2, c3 = st.columns(3)
        with c1:
            klucz_l = st.multiselect("Klucz w lewej", list(dl.columns), key="join_kl")
        with c2:
            klucz_p = st.multiselect("Klucz w prawej", list(dp.columns), key="join_kp")
        with c3:
            rodzaj = st.selectbox("Rodzaj", ["inner", "left", "right", "outer"],
                                  key="join_rodzaj",
                                  help="inner - tylko pasujace pary. left - wszystkie z lewej. "
                                       "outer - wszystko z obu stron.")

        nazwa_join = st.text_input("Nazwa nowego zbioru", f"{lewa}_x_{prawa}", key="join_nazwa",
                                   help="Pod ta nazwa wynik pojawi się na liście zbiorów "
                                        "i jako tabela w zakładce SQL.")

        if klucz_l and klucz_p and len(klucz_l) == len(klucz_p):
            if st.button("Polacz", type="primary", key="btn_join"):
                try:
                    wynik = dl.merge(dp, left_on=klucz_l, right_on=klucz_p,
                                     how=rodzaj, suffixes=("", f"_{prawa}"))
                    nowa = MagazynDanych.dodaj(nazwa_join or f"{lewa}_x_{prawa}", wynik)
                    st.success(f"Utworzono zbiór '{nowa}' - {len(wynik)} wierszy, "
                               f"{len(wynik.columns)} kolumn.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Błąd łączenia: {e}")
        elif klucz_l or klucz_p:
            st.warning("Liczba kolumn klucza po obu stronach musi być taka sama.")


def _sekcja_pivot(raw_df, all_num_cols):
    st.subheader("Tabela przestawna")
    st.caption("Wynik można zapisać jako nowy zbiór i analizować go dalej "
               "na wykresach oraz w detekcji anomalii.")

    c1, c2 = st.columns(2)
    with c1:
        wiersze_pv = st.multiselect("Wiersze (grupowanie)", list(raw_df.columns), key="pv_index")
        wartosci_pv = st.multiselect("Wartości (agregowane)", all_num_cols, key="pv_values")
    with c2:
        kolumny_pv = st.multiselect("Kolumny (opcjonalnie)", list(raw_df.columns), key="pv_cols")
        agregacja = st.selectbox(
            "Funkcja agregująca",
            ["bez agregacji", "sum", "mean", "median", "min", "max", "count", "nunique", "std"],
            key="pv_agg",
            help="'bez agregacji' przestawia dane jeden do jednego, bez łączenia wierszy. "
                 "Wymaga, żeby każda para (wiersz, kolumna) występowała tylko RAZ - inaczej "
                 "nie wiadomo która z kilku wartości wstawić do jednej komórki.")

    st.markdown("#### Czyszczenie wyniku")
    c1, c2, c3 = st.columns(3)
    with c1:
        usun_null = st.checkbox("Usuń wiersze z pustymi wartościami", value=False,
                                help="Wiersze, w których którakolwiek kolumna wynikowa jest pusta.")
    with c2:
        usun_zera = st.checkbox("Usuń wiersze z zerami", value=False,
                                help="Wiersze, w których którakolwiek kolumna wynikowa równa się zero.")
    with c3:
        usun_puste_all = st.checkbox("Usuń wiersze całkiem puste", value=True,
                                     help="Wiersze, w których WSZYSTKIE kolumny wynikowe sa puste.")

    if not (wiersze_pv and wartosci_pv):
        st.info("Wybierz przynajmniej jedna kolumnę w polu Wiersze oraz jedna w polu Wartości.")
        return

    try:
        if agregacja == "bez agregacji":
            # pd.pivot (nie pivot_table) - przestawia dane jeden do jednego.
            # Wywali sie, jesli ta sama para (wiersz, kolumna) powtarza sie w danych.
            if kolumny_pv:
                pv = raw_df.pivot(index=wiersze_pv, columns=kolumny_pv, values=wartosci_pv)
            else:
                # bez kolumn rozwijanych w poziomie nie ma czego przestawiac -
                # zostaja po prostu wybrane kolumny, ustawione jako indeks + wartosci
                pv = raw_df.set_index(wiersze_pv)[wartosci_pv]
        else:
            pv = pd.pivot_table(raw_df, index=wiersze_pv,
                                columns=kolumny_pv if kolumny_pv else None,
                                values=wartosci_pv, aggfunc=agregacja)

        # splaszczenie wielopoziomowych naglowkow - inaczej dalsza analiza jest niemozliwa
        if isinstance(pv.columns, pd.MultiIndex):
            pv.columns = ["_".join(str(x) for x in kol if str(x) != "")
                          for kol in pv.columns]
        pv = pv.reset_index()

        kol_wynikowe = [c for c in pv.columns if c not in wiersze_pv]
        przed = len(pv)

        if usun_puste_all and kol_wynikowe:
            pv = pv.dropna(subset=kol_wynikowe, how="all")
        if usun_null and kol_wynikowe:
            pv = pv.dropna(subset=kol_wynikowe, how="any")
        if usun_zera and kol_wynikowe:
            liczbowe = pv[kol_wynikowe].select_dtypes(include="number").columns
            if len(liczbowe) > 0:
                pv = pv[~(pv[liczbowe] == 0).any(axis=1)]

        usuniete = przed - len(pv)
        if usuniete > 0:
            st.caption(f"Usunięto {usuniete} z {przed} wierszy wyniku.")

        st.dataframe(pv.head(300), width="stretch")
        st.caption(f"Wynik: {len(pv)} wierszy, {len(pv.columns)} kolumn.")

        c1, c2 = st.columns(2)
        with c1:
            nazwa_pv = st.text_input("Nazwa nowego zbioru", "przestawna", key="pv_nazwa")
        with c2:
            st.write("")
            if st.button("Zapisz jako zbiór", type="primary", key="btn_pv"):
                nowa = MagazynDanych.dodaj(nazwa_pv or "przestawna", pv)
                st.success(f"Zapisano jako '{nowa}' i ustawiono jako aktywny.")
                st.rerun()

        Narzedzia.przycisk_pobierania(
            "Pobierz wynik (CSV)", Narzedzia.to_csv_bytes(pv),
            "tabela_przestawna.csv", "text/csv", key="pob_pivot")
    except ValueError as e:
        if "duplicate" in str(e).lower():
            st.error(
                "Nie da się przestawić bez agregacji, bo ta sama para (wiersz, kolumna) "
                "występuje w danych więcej niż raz - do jednej komórki pasowałoby kilka "
                "różnych wartości naraz.\n\n"
                "Wybierz funkcje agregująca (np. sum albo mean), albo dodaj do pola Wiersze "
                "kolumnę, która rozróżnia te powtórzenia."
            )
        else:
            st.error(f"Błąd tworzenia tabeli przestawnej: {e}")
    except Exception as e:
        st.error(f"Błąd tworzenia tabeli przestawnej: {e}")


def _sekcja_sql():
    st.subheader("Zapytanie SQL")

    if duckdb is None:
        st.error("Biblioteka duckdb nie jest zainstalowana. Uruchom: pip install duckdb")
        return

    st.caption("Każdy wczytany zbiór jest dostępny jako tabela pod swoją nazwa. "
               "Działa pełny SQL: JOIN, GROUP BY, podzapytania, funkcje okna.")

    tabele = list(st.session_state.zbiory.keys())
    st.markdown("**Dostępne tabele:**")
    for t in tabele:
        d = st.session_state.zbiory[t]
        st.caption(f"  {t}  ({len(d)} wierszy)  -  kolumny: "
                   + ", ".join(map(str, d.columns[:12]))
                   + (" ..." if len(d.columns) > 12 else ""))

    domyslne = f'SELECT *\nFROM "{tabele[0]}"\nLIMIT 100'
    zapytanie = st.text_area("Zapytanie", value=domyslne, height=160, key="sql_query")

    c1, c2 = st.columns([1, 3])
    with c1:
        wykonaj = st.button("Wykonaj", type="primary")
    with c2:
        nazwa_sql = st.text_input("Nazwa zbioru wynikowego", "wynik_sql",
                                  key="sql_nazwa", label_visibility="collapsed")

    if wykonaj and zapytanie.strip():
        try:
            con = duckdb.connect()
            for t, d in st.session_state.zbiory.items():
                con.register(t, d)  # nazwa zbioru staje sie nazwa tabeli
            wynik_sql = con.execute(zapytanie).df()
            con.close()
            st.session_state["sql_wynik"] = wynik_sql
        except Exception as e:
            st.session_state["sql_wynik"] = None
            st.error(f"Błąd zapytania: {e}")

    wynik_sql = st.session_state.get("sql_wynik")
    if wynik_sql is not None:
        st.success(f"Zwrócono {len(wynik_sql)} wierszy, {len(wynik_sql.columns)} kolumn.")
        st.dataframe(wynik_sql.head(300), width="stretch")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Zapisz wynik jako zbiór", type="primary", key="btn_sql_save"):
                nowa = MagazynDanych.dodaj(nazwa_sql or "wynik_sql", wynik_sql)
                st.success(f"Zapisano jako '{nowa}' i ustawiono jako aktywny.")
                st.rerun()
        with c2:
            Narzedzia.przycisk_pobierania(
                "Pobierz wynik (CSV)", Narzedzia.to_csv_bytes(wynik_sql),
                "wynik_sql.csv", "text/csv", key="pob_sql")



def _odduplikuj_kolumny(df):
    """Po zmianie nazw dwie kolumny mogą dostać te sama nazwę - wtedy pandas
    przy odwołaniu zwraca kilka kolumn naraz i wszystko się sypie.
    Dopisujemy numer do powtórzeń."""
    nowe, licznik = [], {}
    for c in df.columns:
        c = str(c)
        if c in licznik:
            licznik[c] += 1
            nowe.append(f"{c}_{licznik[c]}")
        else:
            licznik[c] = 1
            nowe.append(c)
    df = df.copy()
    df.columns = nowe
    return df


def _sekcja_nazwy_kolumn(raw_df):
    """
    Zmiana nazw kolumn na podstawie słownika z innego wczytanego zbioru.

    Typowa sytuacja w danych urzędowych: właściwy plik ma kolumny nazwane
    kodami (a01, a02, a03...), a osobny plik-słownik opisuje co każdy kod
    oznacza. Ta sekcja łączy jedno z drugim.
    """
    st.subheader("Zmiana nazw kolumn")

    tryb = st.radio("Sposob", ["Ze słownika (inny wczytany plik)", "Recznie"],
                    horizontal=True, key="tryb_nazwy")

    # ---------------- ze slownika ----------------
    if tryb.startswith("Ze słownika"):
        inne = [n for n in st.session_state.zbiory if n != st.session_state.aktywny]
        if not inne:
            st.info("Wgraj drugi plik ze słownikiem nazw - taki, który w jednej kolumnie ma "
                    "kody odpowiadające nazwom kolumn, a w innej ich pełne nazwy.")
            return

        c1, c2, c3 = st.columns(3)
        with c1:
            nazwa_sl = st.selectbox("Zbiór ze słownikiem", inne, key="sl_zbior")
        slownik = st.session_state.zbiory[nazwa_sl]
        with c2:
            kol_kod = st.selectbox("Kolumna z kodem", list(slownik.columns), key="sl_kod",
                                   help="Wartości z tej kolumny będą dopasowywane do obecnych "
                                        "nazw kolumn analizowanego zbioru.")
        with c3:
            kol_nazwa = st.multiselect("Kolumny z nazwa", list(slownik.columns), key="sl_nazwa",
                                       help="Źródło nowej nazwy. Można wybrać kilka - zostaną "
                                            "połączone separatorem.")

        if not kol_nazwa:
            st.info("Wybierz przynajmniej jedna kolumnę z nazwa.")
            return

        c1, c2, c3 = st.columns(3)
        with c1:
            sep_nazw = st.text_input("Separator", " | ", key="sl_sep")
        with c2:
            maks_dl = Pola.num_field("Maks. długość nazwy", 5, 300, 60, 5, "sl_maxdl",
                                     help="Długie opisy sa obcinane. Nazwy dłuższe niż kilkadziesiąt "
                                          "znaków sa nieczytelne w tabelach i na wykresach.")
        with c3:
            zachowaj_kod = st.checkbox("Zachowaj kod w nazwie", value=True,
                                       help="Nowa nazwa będzie postaci 'a01 - Gotowka w kasie'. "
                                            "Ulatwia odnalezienie się w danych po zmianie.")

        # Slownik ma zwykle wiele wierszy na ten sam kod (np. jeden na kazdy okres).
        # Bierzemy pierwsze wystapienie kazdego kodu - reszta to powtorzenia.
        sl = slownik.dropna(subset=[kol_kod]).copy()
        przed = len(sl)
        sl = sl.drop_duplicates(subset=[kol_kod], keep="first")
        if przed > len(sl):
            st.caption(f"Słownik ma {przed} wierszy, ale tylko {len(sl)} unikalnych kodów - "
                       f"dla powtórzeń wzięte zostało pierwsze wystąpienie.")

        mapowanie = {}
        for _, w in sl.iterrows():
            kod = str(w[kol_kod]).strip()
            czesci = [str(w[k]).strip() for k in kol_nazwa
                      if pd.notna(w[k]) and str(w[k]).strip() not in ("", "nan")]
            if not czesci:
                continue
            nowa = sep_nazw.join(czesci)
            if len(nowa) > maks_dl:
                nowa = nowa[:maks_dl].rstrip() + "..."
            if zachowaj_kod:
                nowa = f"{kod} - {nowa}"
            mapowanie[kod] = nowa

        obecne = [str(c) for c in raw_df.columns]
        trafione = {c: mapowanie[c] for c in obecne if c in mapowanie}
        nietrafione = [c for c in obecne if c not in mapowanie]

        c1, c2 = st.columns(2)
        c1.metric("Kolumny do zmiany", len(trafione))
        c2.metric("Bez dopasowania", len(nietrafione))

        if not trafione:
            st.warning(
                "Żadna kolumna nie pasuje do kodów ze słownika. Sprawdź, czy wybrana kolumna "
                "z kodem jest właściwa - jej wartości muszą być dokładnie takie same jak nazwy "
                "kolumn analizowanego zbioru."
            )
            with st.expander("Podgląd: co jest po obu stronach"):
                st.caption("Nazwy kolumn analizowanego zbioru:")
                st.text(", ".join(obecne[:30]))
                st.caption(f"Przykładowe kody z kolumny '{kol_kod}':")
                st.text(", ".join(map(str, sl[kol_kod].head(30).tolist())))
            return

        # Ostrzezenie o nierozroznialnych nazwach. Czesty przypadek: wybrane kolumny
        # slownika maja dlugi wspolny prefiks, przez co po obcieciu do limitu wszystkie
        # koncza sie tak samo. Bez kodu w nazwie takie kolumny sa nie do odroznienia.
        nowe_nazwy = list(trafione.values())
        powtorzone = len(nowe_nazwy) - len(set(nowe_nazwy))
        if powtorzone > 0:
            st.warning(
                f"{powtorzone} z {len(nowe_nazwy)} nowych nazw powtarza się. Do powtórzeń zostanie "
                "dopisany numer, ale kolumny będą trudne do odróżnienia.\n\n"
                "Co pomaga: zaznaczyć 'Zachowaj kod w nazwie', zwiększyć maksymalna długość "
                "albo wybrać inna kolumnę słownika - taka, która faktycznie rozróżnia pola, "
                "a nie powtarza ten sam nagłówek działu."
            )

        st.markdown("#### Podgląd zmian")
        st.dataframe(pd.DataFrame({"Obecna nazwa": list(trafione.keys()),
                                   "Nowa nazwa": list(trafione.values())}),
                     width="stretch", hide_index=True)

        if nietrafione:
            with st.expander(f"Kolumny bez dopasowania ({len(nietrafione)}) - zostaną bez zmian"):
                st.text(", ".join(nietrafione))

        c1, c2 = st.columns(2)
        with c1:
            nazwa_wyniku = st.text_input("Nazwa nowego zbioru",
                                         f"{st.session_state.aktywny}_nazwane", key="sl_nazwa_zb")
        with c2:
            st.write("")
            if st.button("Zmień nazwy", type="primary", key="btn_sl"):
                wynik = _odduplikuj_kolumny(raw_df.rename(columns=trafione))
                nowa = MagazynDanych.dodaj(nazwa_wyniku or "nazwane", wynik)
                st.success(f"Utworzono zbiór '{nowa}' - zmieniono {len(trafione)} nazw kolumn.")
                st.rerun()

    # ---------------- recznie ----------------
    else:
        st.caption("Popraw nazwy w tabeli. Puste pole zostawia nazwę bez zmian.")

        zmiany = st.data_editor(
            pd.DataFrame({"Obecna nazwa": [str(c) for c in raw_df.columns],
                          "Nowa nazwa": ["" for _ in raw_df.columns]}),
            width="stretch", hide_index=True, key="edytor_nazw",
            disabled=["Obecna nazwa"],
        )

        mapa = {r["Obecna nazwa"]: r["Nowa nazwa"].strip()
                for _, r in zmiany.iterrows()
                if isinstance(r["Nowa nazwa"], str) and r["Nowa nazwa"].strip()}

        c1, c2 = st.columns(2)
        with c1:
            nazwa_wyniku = st.text_input("Nazwa nowego zbioru",
                                         f"{st.session_state.aktywny}_nazwane", key="rec_nazwa_zb")
        with c2:
            st.write("")
            if st.button("Zmień nazwy", type="primary", key="btn_rec", disabled=not mapa):
                wynik = _odduplikuj_kolumny(raw_df.rename(columns=mapa))
                nowa = MagazynDanych.dodaj(nazwa_wyniku or "nazwane", wynik)
                st.success(f"Utworzono zbiór '{nowa}' - zmieniono {len(mapa)} nazw kolumn.")
                st.rerun()

        if mapa:
            st.caption(f"Do zmiany: {len(mapa)} kolumn.")


def renderuj():
    raw_df = MagazynDanych.aktywny_df()
    all_num_cols = list(raw_df.select_dtypes(include="number").columns)

    sek = st.radio(
        "Sekcja", ["Podglad", "Porównanie zbiorów", "Łączenie tabel", "Nazwy kolumn",
                   "Tabela przestawna", "SQL"],
        horizontal=True, key="sekcja_dane",
    )

    if sek == "Podglad":
        _sekcja_podglad(raw_df, all_num_cols)
    elif sek == "Porównanie zbiorów":
        _sekcja_porownanie()
    elif sek == "Łączenie tabel":
        _sekcja_laczenie()
    elif sek == "Nazwy kolumn":
        _sekcja_nazwy_kolumn(raw_df)
    elif sek == "Tabela przestawna":
        _sekcja_pivot(raw_df, all_num_cols)
    else:
        _sekcja_sql()