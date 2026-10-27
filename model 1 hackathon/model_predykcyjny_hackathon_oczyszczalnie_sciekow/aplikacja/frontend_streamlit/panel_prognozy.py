"""
Panel boczny - wzorowany na panel_boczny.py z Detektora GUS (wgrywanie plikow CSV / Excel, wybor zbioru aktywnego,
limit punktow). Dochodzi jedno: pliki w formacie zuzycia energii (licznik jak mock_*, raport dystrybutora, czas;kwh)
sa rozpoznawane automatycznie i staja sie DANYMI DO PROGNOZY, a ponizej wybiera sie pompownie (wykrywana z nazwy).
Pozostale pliki laduja sie jak w GUS - do podgladu i obrobki w zakladce Dane.
"""

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from frontend_streamlit.magazyn_danych import MagazynDanych

MIASTA = {"Rybnik": "RY", "Ruda Śląska": "RU", "Chorzów": "CH"}
NOWA = "nowa pompownia"


def _jako_prognoza(u, sep, kodowanie, wiersz_naglowka=1):
    """Probuje odczytac plik (CSV albo Excel) jako dane zuzycia energii. Zwraca (godzinowo, format) albo (None, None)."""
    import model.prognoza as P
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(u.name).suffix) as t:
        t.write(u.getvalue())
    try:
        if u.name.lower().endswith((".xlsx", ".xls")):
            nowe, rodzaj = P.wczytaj_excel(t.name, wiersz_naglowka=wiersz_naglowka)
        else:
            nowe, rodzaj = P.wczytaj_plik(t.name, sep=sep, kodowanie=kodowanie)
        return (nowe, rodzaj) if len(nowe) and nowe["kwh"].notna().any() else (None, None)
    except Exception:
        return None, None


def _tabela_godzinowa(nowe):
    lok = nowe["czas"].dt.tz_convert("Europe/Warsaw")
    return pd.DataFrame({"czas": lok.dt.strftime("%Y-%m-%d %H:%M"), "dzien_tygodnia": lok.dt.day_name(),
                         "kwh": nowe["kwh"].round(3).values})


def _pompownia(dp):
    """Wybor pompowni dla danych do prognozy (wykrywana z nazwy pliku, mozna zmienic)."""
    import model.prognoza as P
    d = st.session_state.get("d_baza")
    obiekty = sorted(d["energia"]["obiekt_id"].unique()) if d is not None else []
    zgadniety = P._obiekt_z_nazwy(dp["pliki"][0])
    opcje = obiekty + [NOWA]
    wybor = st.sidebar.selectbox("Pompownia", opcje, key="pp_obiekt",
                                 index=opcje.index(zgadniety) if zgadniety in opcje else len(opcje) - 1,
                                 help="Wykrywana z nazwy pliku - zmień, jeśli się nie zgadza.")
    stacja = None
    if wybor == NOWA:
        oid = st.sidebar.text_input("Nazwa pompowni", value=zgadniety if zgadniety not in obiekty else "NOWA", key="pp_nazwa")
        stacja = MIASTA[st.sidebar.selectbox("Miasto (pogoda)", list(MIASTA), key="pp_miasto")]
    else:
        oid = wybor
    klucz = (tuple(dp["pliki"]), oid, stacja)
    if st.session_state.get("pp_klucz") != klucz:                 # inne dane albo pompownia -> stary wynik nieaktualny
        st.session_state.pp_klucz = klucz
        st.session_state.prog_wynik = None
    dp.update(oid=oid, stacja=stacja)
    st.session_state.dane_prognozy = dp


def renderuj():
    """Caly panel boczny. Wywolac raz, przed zakladkami."""
    st.sidebar.title("Dane wejściowe")

    uploaded = st.sidebar.file_uploader(
        "Wgraj pliki CSV lub Excel", type=["csv", "txt", "xlsx", "xls"], accept_multiple_files=True, key="pp_pliki",
        help="Pliki z zużyciem energii (licznik, raport dystrybutora, czas;kwh) są rozpoznawane automatycznie. "
             "Inne pliki - do podglądu w zakładce Dane.",
    )

    if uploaded:
        ma_excel = any(u.name.lower().endswith((".xlsx", ".xls")) for u in uploaded)
        wiersz_naglowka = st.sidebar.number_input(
            "Wiersz nagłówka (Excel)", min_value=1, value=1, step=1,
            help="Więcej niż 1, jeśli arkusz zaczyna się tytułem.") if ma_excel else 1
        ma_csv = any(u.name.lower().endswith((".csv", ".txt")) for u in uploaded)
        if ma_csv:
            sep_wybor = st.sidebar.selectbox("Separator (CSV)", ["automatycznie", ";", ",", "\t", "|"], index=0, key="pp_sep")
            kodowanie = st.sidebar.text_input("Kodowanie (CSV)", value="automatycznie", key="pp_kod",
                                              help="automatycznie, utf-8 albo cp1250 (Windows-1250)")
        else:
            sep_wybor, kodowanie = "automatycznie", "automatycznie"
        sep = None if sep_wybor == "automatycznie" else sep_wybor
        kod = None if kodowanie.strip().lower() in ("", "automatycznie") else kodowanie.strip()

        if st.sidebar.button("Wczytaj pliki", type="primary", width="stretch", key="pp_wczytaj"):
            prognoza = []
            for u in uploaded:
                try:
                    if u.name.lower().endswith((".xlsx", ".xls")):
                        arkusze = pd.ExcelFile(u).sheet_names
                        nowe, rodzaj = _jako_prognoza(u, sep, kod, int(wiersz_naglowka))
                        df_new = _tabela_godzinowa(nowe) if nowe is not None else \
                            pd.read_excel(u, sheet_name=0, header=int(wiersz_naglowka) - 1)
                        if len(arkusze) > 1:
                            st.sidebar.info(f"{u.name}: wczytano tylko pierwszy arkusz ('{arkusze[0]}' z {len(arkusze)}).")
                    else:
                        nowe, rodzaj = _jako_prognoza(u, sep, kod)
                        df_new = _tabela_godzinowa(nowe) if nowe is not None else \
                            pd.read_csv(u, sep=sep, engine="python", encoding=kod or "utf-8", encoding_errors="replace")
                    df_new = MagazynDanych.sprzataj_kolumny(df_new)
                    nazwa = MagazynDanych.dodaj(u.name.rsplit(".", 1)[0], df_new)
                    if nowe is not None:
                        prognoza.append((u.name, nowe, rodzaj))
                        st.sidebar.success(f"{nazwa}: {len(df_new)} godzin · dane do prognozy ({rodzaj})")
                    else:
                        st.sidebar.success(f"{nazwa}: {len(df_new)} wierszy")
                except Exception as e:
                    st.sidebar.error(f"{u.name} - blad wczytywania: {e}")
            if prognoza:
                nowe = pd.concat([p[1] for p in prognoza]).sort_values("czas").drop_duplicates("czas", keep="last")
                st.session_state.dane_prognozy = dict(
                    pliki=[p[0] for p in prognoza], nowe=nowe.reset_index(drop=True),
                    rodzaj=", ".join(sorted({p[2] for p in prognoza})),
                    zrodlo=prognoza[0][0] + (f" + {len(prognoza) - 1} inne" if len(prognoza) > 1 else ""))
                st.session_state.pp_klucz = None

    if st.session_state.zbiory:
        st.sidebar.divider()
        st.session_state.aktywny = st.sidebar.selectbox(
            "Zbiór aktywny", list(st.session_state.zbiory.keys()),
            index=list(st.session_state.zbiory.keys()).index(st.session_state.aktywny)
            if st.session_state.aktywny in st.session_state.zbiory else 0,
            help="Dla zakładek Dane i Wykresy.")
        akt = st.session_state.zbiory[st.session_state.aktywny]
        st.sidebar.caption(f"Wierszy: {len(akt)} | Kolumn: {len(akt.columns)} | "
                           f"Zbiorów: {len(st.session_state.zbiory)}")

    dp = st.session_state.get("dane_prognozy")
    if dp is not None:
        st.sidebar.divider()
        lok = dp["nowe"]["czas"].dt.tz_convert("Europe/Warsaw")
        st.sidebar.markdown("**Dane pompowni**")
        st.sidebar.caption(f"{dp['zrodlo']} · {len(dp['nowe']):,} godzin · {lok.min():%d.%m.%Y} – {lok.max():%d.%m.%Y}".replace(",", " "))
        _pompownia(dp)

    if st.session_state.zbiory:
        st.sidebar.divider()
        st.session_state.limit_punktow = st.sidebar.number_input(
            "Maks. punktów na wykresie", min_value=0, value=st.session_state.limit_punktow, step=1000,
            help="0 = bez limitu. Limit przyspiesza rysowanie dużych zbiorów.")
