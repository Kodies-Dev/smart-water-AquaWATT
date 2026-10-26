"""
Panel boczny pod predykcje: tu wczytuje sie DANE DO PROGNOZY (plik albo pompownia z bazy) - raz, w jednym miejscu.
Wczytane dane trafiaja do zakladki Dane (ogladanie, statystyki, SQL...) i do zakladki Prognoza (jeden przycisk).
Zastepuje panel_boczny.py z Detektora GUS (ten plik zostaje bez zmian).
"""

import hashlib
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

MIASTA = {"Rybnik": "RY", "Ruda Śląska": "RU", "Chorzów": "CH"}
NOWA = "nowa pompownia (spoza bazy)"
ZBIOR = "dane_do_prognozy"
POMOC_PLIK = ("Formaty rozpoznawane automatycznie: odczyty licznika (data;godzina;typ;wartosc;status, jak pliki mock_*), "
              "raport dystrybutora (Rap_godzinowy) albo dwie kolumny czas;kwh. Separator i kodowanie też.")


def _wczytaj_plik(plik):
    """Parsowanie z pamiecia podreczna - ten sam plik nie jest czytany od nowa przy kazdym kliknieciu."""
    import model.prognoza as P
    dane = plik.getvalue()
    h = hashlib.md5(dane).hexdigest()
    pam = st.session_state.get("pp_cache")
    if pam and pam[0] == h:
        return pam[1], pam[2]
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(plik.name).suffix) as t:
        t.write(dane)
    nowe, rodzaj = P.wczytaj_plik(t.name)
    st.session_state.pp_cache = (h, nowe, rodzaj)
    return nowe, rodzaj


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
        st.session_state.pp_aktywny = ZBIOR          # wybor zbioru nizej w panelu tez przechodzi na nowe dane
    st.session_state.dane_prognozy = dp


def renderuj():
    st.sidebar.title("Prognoza energii")
    d = st.session_state.get("d_baza")
    obiekty = sorted(d["energia"]["obiekt_id"].unique()) if d is not None else []

    st.sidebar.markdown("**Dane do prognozy**")
    zrodlo = st.sidebar.radio("Skąd dane", ["Plik z danymi", "Pompownia z bazy"], key="pp_zrodlo", horizontal=True,
                              label_visibility="collapsed")
    if zrodlo == "Plik z danymi":
        plik = st.sidebar.file_uploader("Plik CSV / TXT", type=["csv", "txt"], key="pp_plik", help=POMOC_PLIK)
        if plik is None:
            st.session_state.dane_prognozy = None
            st.sidebar.caption("Wgraj plik z odczytami zużycia energii pompowni (co najmniej ok. 5 tygodni).")
        else:
            import model.prognoza as P
            try:
                nowe, rodzaj = _wczytaj_plik(plik)
            except Exception as e:
                st.session_state.dane_prognozy = None
                st.sidebar.error(f"Nie udało się odczytać pliku: {e}. Najprościej: dwie kolumny czas;kwh.")
                nowe = None
            if nowe is not None:
                lok = nowe["czas"].dt.tz_convert("Europe/Warsaw")
                st.sidebar.success(f"{len(nowe):,} godzin · {lok.min():%d.%m.%Y} – {lok.max():%d.%m.%Y}\n\n"
                                   f"razem {nowe['kwh'].sum():,.0f} kWh · format: {rodzaj}".replace(",", " "))
                zgadniety = P._obiekt_z_nazwy(plik.name)
                opcje = obiekty + [NOWA]
                wybor = st.sidebar.selectbox("Której pompowni dotyczy plik?", opcje, key="pp_obiekt",
                                             index=opcje.index(zgadniety) if zgadniety in opcje else len(opcje) - 1,
                                             help="Pompownia z bazy = wcześniejsze tygodnie dobierzemy z bazy.")
                stacja = None
                if wybor == NOWA:
                    oid = st.sidebar.text_input("Nazwa pompowni", value=zgadniety if zgadniety not in obiekty else "NOWA",
                                                key="pp_nazwa")
                    stacja = MIASTA[st.sidebar.selectbox("Miasto (pogoda)", list(MIASTA), key="pp_miasto")]
                else:
                    oid = wybor
                _ustaw(dict(zrodlo=plik.name, rodzaj=rodzaj, oid=oid, stacja=stacja, nowe=nowe,
                            hash=st.session_state.pp_cache[0]), _do_podgladu(nowe))
    else:
        if not obiekty:
            st.sidebar.warning("Brak danych z bazy.")
            st.session_state.dane_prognozy = None
        else:
            oid = st.sidebar.selectbox("Pompownia", obiekty, key="pp_obiekt_baza",
                                       index=obiekty.index("RY_PZ1") if "RY_PZ1" in obiekty else 0)
            e = d["energia"][d["energia"]["obiekt_id"] == oid]
            hist = e[e["czas"] > e["czas"].max() - pd.Timedelta(weeks=8)][["czas", "kwh"]]
            st.sidebar.caption(f"Prognoza na dobę po ostatniej godzinie w bazie ({e['czas'].max().tz_convert('Europe/Warsaw'):%d.%m.%Y}). "
                               f"W zakładce Dane: ostatnie 8 tygodni.")
            _ustaw(dict(zrodlo="baza danych", rodzaj="baza", oid=oid, stacja=None, nowe=None, hash=None), _do_podgladu(hist))

    st.sidebar.divider()
    with st.sidebar.expander("Baza danych"):
        if d is not None:
            st.caption(f"Połączono: {len(obiekty)} pompowni, " + f"{len(d['energia']):,} godzin zużycia.".replace(",", " "))
        else:
            st.caption("Brak połączenia z bazą – uruchom `docker compose up -d db`.")
        if st.button("Odśwież dane z bazy", key="pp_odswiez", width="stretch"):
            try:
                from backend_ml_llm.nasz_detektor import nasz_detektor
                with st.spinner("Wczytuję..."):
                    st.session_state.d_baza, st.session_state.alarmy = nasz_detektor.dane_z_bazy()
                st.session_state.zbiory["baza_dobowo"] = nasz_detektor.dobowo_do_podgladu(st.session_state.d_baza)
                st.rerun()
            except Exception as e:
                st.error(f"Nie udało się: {e}")

    if st.session_state.zbiory:
        with st.sidebar.expander("Zbiór w zakładkach Dane i Wykresy"):
            nazwy = list(st.session_state.zbiory)
            st.session_state.aktywny = st.selectbox(
                "Zbiór", nazwy, index=nazwy.index(st.session_state.aktywny) if st.session_state.aktywny in nazwy else 0,
                key="pp_aktywny", help="dane_do_prognozy = to, co wczytałeś powyżej; baza_dobowo = wszystkie pompownie dobowo.")
            st.session_state.limit_punktow = st.number_input(
                "Maks. punktów na wykresie", min_value=0, value=st.session_state.limit_punktow, step=1000,
                help="0 = wszystkie punkty.")
