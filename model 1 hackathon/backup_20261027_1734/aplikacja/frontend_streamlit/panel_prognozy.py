"""
Panel boczny pod predykcje: tu wczytuje sie DANE DO PROGNOZY - plik albo kilka plikow tej samej pompowni,
separator, kodowanie i wybor pompowni (wykrywanej sama z nazwy pliku). Wczytane dane trafiaja do zakladki Dane
i do zakladki Prognoza. Zastepuje panel_boczny.py z Detektora GUS (ten plik zostaje bez zmian).
"""

import hashlib
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

MIASTA = {"Rybnik": "RY", "Ruda Śląska": "RU", "Chorzów": "CH"}
NOWA = "nowa pompownia (spoza bazy)"
ZBIOR = "dane_do_prognozy"
SEPARATORY = {"automatycznie": None, "; (średnik)": ";", ", (przecinek)": ",", "tabulator": "\t", "| (kreska)": "|"}
KODOWANIA = {"automatycznie": None, "UTF-8": "utf-8-sig", "Windows-1250": "cp1250"}
POMOC_PLIK = ("Odczyty licznika (data;godzina;typ;wartosc;status, jak pliki mock_*), raport dystrybutora (Rap_godzinowy) "
              "albo dwie kolumny czas;kwh. Kilka plików tej samej pompowni (np. miesiące osobno) zostanie sklejonych.")


def _wczytaj(pliki, sep, kodowanie):
    """Parsowanie z pamiecia podreczna - te same pliki i ustawienia nie sa czytane od nowa przy kazdym kliknieciu."""
    import model.prognoza as P
    h = hashlib.md5(b"".join(p.getvalue() for p in pliki) + f"{sep}|{kodowanie}".encode()).hexdigest()
    pam = st.session_state.get("pp_cache")
    if pam and pam[0] == h:
        return pam[1], pam[2], h
    sciezki = []
    for p in pliki:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(p.name).suffix) as t:
            t.write(p.getvalue())
            sciezki.append(t.name)
    nowe, rodzaj = P.wczytaj_pliki(sciezki, sep=sep, kodowanie=kodowanie)
    st.session_state.pp_cache = (h, nowe, rodzaj)
    return nowe, rodzaj, h


def _do_podgladu(nowe):
    lok = nowe["czas"].dt.tz_convert("Europe/Warsaw")
    return pd.DataFrame({"czas": lok.dt.strftime("%Y-%m-%d %H:%M"), "dzien_tygodnia": lok.dt.day_name(),
                         "kwh": nowe["kwh"].round(3).values})


def _ustaw(dp, podglad):
    """Zapisuje dane do prognozy; gdy sie zmienily - czysci stary wynik i podmienia zbior w zakladce Dane."""
    klucz = (dp["zrodlo"], dp["oid"], dp.get("stacja"), dp.get("hash"))
    if st.session_state.get("pp_klucz") != klucz:
        st.session_state.pp_klucz = klucz
        st.session_state.prog_wynik = None
        st.session_state.zbiory[ZBIOR] = podglad
        st.session_state.aktywny = ZBIOR
        st.session_state.dp_aktywny = ZBIOR          # wybor „Zbior aktywny” w zakladce Dane tez przechodzi na nowe dane
    st.session_state.dane_prognozy = dp


def renderuj():
    import model.prognoza as P
    st.sidebar.title("Prognoza energii")
    st.sidebar.markdown("**Dane do prognozy**")
    d = st.session_state.get("d_baza")
    obiekty = sorted(d["energia"]["obiekt_id"].unique()) if d is not None else []

    pliki = st.sidebar.file_uploader("Plik(i) CSV / TXT", type=["csv", "txt"], accept_multiple_files=True, key="pp_plik",
                                     help=POMOC_PLIK)
    c1, c2 = st.sidebar.columns(2)
    sep = SEPARATORY[c1.selectbox("Separator", list(SEPARATORY), key="pp_sep")]
    kod = KODOWANIA[c2.selectbox("Kodowanie", list(KODOWANIA), key="pp_kod")]
    if not pliki:
        st.session_state.dane_prognozy = None
        st.sidebar.caption("Wgraj odczyty zużycia energii pompowni – co najmniej ok. 5 tygodni (dla pompowni z bazy wystarczy mniej).")
        return
    try:
        nowe, rodzaj, h = _wczytaj(pliki, sep, kod)
    except Exception as e:
        st.session_state.dane_prognozy = None
        st.sidebar.error(f"Nie udało się odczytać pliku: {e}. Sprawdź separator i kodowanie albo przygotuj dwie kolumny czas;kwh.")
        return
    if nowe.empty or nowe["kwh"].notna().sum() == 0:
        st.session_state.dane_prognozy = None
        st.sidebar.error("W pliku nie znaleziono odczytów zużycia - sprawdź separator i kodowanie.")
        return
    lok = nowe["czas"].dt.tz_convert("Europe/Warsaw")
    ile = f"{len(pliki)} pliki · " if len(pliki) > 1 else ""
    st.sidebar.success(f"{ile}{len(nowe):,} godzin · {lok.min():%d.%m.%Y} – {lok.max():%d.%m.%Y}\n\n"
                       f"razem {nowe['kwh'].sum():,.0f} kWh · format: {rodzaj}".replace(",", " "))

    zgadniety = P._obiekt_z_nazwy(pliki[0].name)
    opcje = obiekty + [NOWA]
    wybor = st.sidebar.selectbox("Której pompowni dotyczy plik?", opcje, key="pp_obiekt",
                                 index=opcje.index(zgadniety) if zgadniety in opcje else len(opcje) - 1,
                                 help="Wykrywana z nazwy pliku - zmień, jeśli się nie zgadza. Pompownia z bazy = wcześniejsze "
                                      "tygodnie dobierzemy z bazy.")
    stacja = None
    if wybor == NOWA:
        oid = st.sidebar.text_input("Nazwa pompowni", value=zgadniety if zgadniety not in obiekty else "NOWA", key="pp_nazwa")
        stacja = MIASTA[st.sidebar.selectbox("Miasto (pogoda)", list(MIASTA), key="pp_miasto")]
    else:
        oid = wybor
    zrodlo = pliki[0].name + (f" + {len(pliki) - 1} inne" if len(pliki) > 1 else "")
    _ustaw(dict(zrodlo=zrodlo, rodzaj=rodzaj, oid=oid, stacja=stacja, nowe=nowe, hash=h), _do_podgladu(nowe))
