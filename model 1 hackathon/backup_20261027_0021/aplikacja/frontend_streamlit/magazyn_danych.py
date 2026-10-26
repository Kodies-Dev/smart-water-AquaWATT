"""
Zarzadzanie zbiorami danych w pamieci sesji - wgrane pliki, ktory jest
aktywny, i caly stan zwiazany z generowaniem raportu i pytaniami.

Wszystko co dotyczy st.session_state siedzi tutaj, zeby nie grzebac po
calym kodzie w poszukiwaniu gdzie co jest inicjalizowane.
"""

import streamlit as st
import pandas as pd
# limit punktow na wykresach - 0 znaczy bez ograniczen, wszystkie punkty.
# Wartosc mozna zmienic w panelu bocznym - przy bardzo duzych zbiorach
# probkowanie przyspiesza rysowanie.
DOMYSLNY_LIMIT_PUNKTOW = 0


class MagazynDanych:
    """Opakowanie na st.session_state - trzyma wiele wczytanych zbiorow
    naraz (nazwa -> DataFrame). Jeden z nich jest aktywny i to on idzie
    do wykresow i detekcji."""

    @staticmethod
    def inicjalizuj():
        """Wywolac raz, na starcie app.py, zanim cokolwiek innego dotknie
        session_state."""
        for key in ["result_df", "num_cols", "report", "aktywny",
                    "gen_model"]:  # wynikowe dane, nummery kolumn, txt raportu, wybrane dane do raportu, wybrany model
            st.session_state.setdefault(key, None)  # tworzy klucze jesli ich nie ma
            # i przypisuje wartosc none, jak istnieja to je zostawia

        # wiele zbiorow naraz: nazwa -> DataFrame. Zbior aktywny idzie do wykresow i detekcji. slowniki
        st.session_state.setdefault("zbiory", {})  # tutaj trzymamy zbiory, pliki, dane

        st.session_state.setdefault("limit_punktow", DOMYSLNY_LIMIT_PUNKTOW)  # limit punktow na wykresach

        # stan generowania raportu partiami (zeby dalo sie je zatrzymac)
        st.session_state.setdefault("gen_trwa", False)
        st.session_state.setdefault("gen_indeks", 0)  # indeks gdzie jestesmy, postep
        st.session_state.setdefault("gen_czesci", [])  # kolejne wygenerowane czesci raportu
        st.session_state.setdefault("historia_pytan", [])  # pytania i odpowiedzi, historia

    @staticmethod
    def wolna_nazwa(baza: str):
        """Nie nadpisujemy istniejacego zbioru - dopisujemy numer.
        sprawdza unikalnosc nazwy zbioru odaje do tych slownikow steamlitowych z session  state"""
        if baza not in st.session_state.zbiory:  # jesli nazwa nie istnieje w pamieci to hit
            return baza
        i = 2  # jesli jest to tworzymy wariant z numerem od 2 zaczynajac
        while f"{baza}_{i}" in st.session_state.zbiory:  # jezeli numer zajety to i++
            i += 1
        return f"{baza}_{i}"

    @staticmethod
    def dodaj(nazwa: str, df, ustaw_aktywny=True):
        nazwa = MagazynDanych.wolna_nazwa(nazwa)
        st.session_state.zbiory[nazwa] = df
        if ustaw_aktywny:
            st.session_state.aktywny = nazwa
            st.session_state.result_df = None
            st.session_state.report = None
        return nazwa

    @staticmethod
    def usun(nazwa: str):
        """Usuwa zbior z pamieci i przelacza na inny, jesli jakis zostal."""
        del st.session_state.zbiory[nazwa]
        st.session_state.aktywny = (list(st.session_state.zbiory)[0]
                                    if st.session_state.zbiory else None)
        st.session_state.result_df = None

    @staticmethod
    def aktywny_df():
        """Zwraca DataFrame aktualnie wybranego zbioru."""
        return st.session_state.zbiory[st.session_state.aktywny]

    @staticmethod
    def sprzataj_kolumny(df: pd.DataFrame):
        """Usuwa kolumny bez nazwy - Excel dokleja je przy pustych naglowkach."""
        return df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed:")]
