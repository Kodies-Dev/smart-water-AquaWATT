"""
Wlasne pola formularza - liczby z przycinaniem zamiast suwakow, oraz
reczne zakresy osi wykresow.

Napisane bo standardowe suwaki streamlita byly niewygodne przy duzych
zakresach (np. tysiace wierszy) i nie dawaly wpisac konkretnej liczby
z klawiatury - trzeba bylo przesuwac paluchem az sie trafi.
"""

import streamlit as st


class Pola:
    """Wszystkie niestandardowe widgety liczbowe uzywane w zakladkach."""

    @staticmethod
    def clamp(value, low, high, default):
        """sluzy do przycinania wartosci na wykresach mi i max"""
        if value is None:
            return default, False  # tutaj zwracamy defaulta, false - wszystko prawidlowe
        if value < low:
            return low, True  # blad, nie moze byc np mniejsze niz 0
        if value > high:
            return high, True  # nie moze byc wieksze niz ilestam
        return value, False  # to co wpisal skurzybyk

    @staticmethod
    def num_field(label, low, high, default, step, key, help=None, is_int=True):
        """Pole liczbowe bez suwaka. Bez min/max na widgecie, zeby dalo sie wpisac
        cokolwiek - wartosc jest potem przycinana do dopuszczalnego zakresu."""
        raw = st.number_input(
            label,
            value=None,
            step=step,
            key=key,  # klucz zawsze musi byc unikalny
            placeholder=f"domyslnie {default} (zakres {low}-{high})",
            help=help,
        )  # pole liczbowe - pobaw sie potem w wylaczanie tych brzydkich strzalek
        value, clamped = Pola.clamp(raw, low, high, default)  # wartosc i czy blednie wpisana, opis fnkcji wyzej
        if clamped:  # jak poza max/min tu low high
            st.caption(f"Wartosc poza zakresem {low}-{high} - uzyto {value}.")
        return int(value) if is_int else float(value)

    @staticmethod
    def axis_fields(key_prefix, cols=4):
        """Cztery pola: X od/do, Y od/do. Puste = zakres automatyczny.
        funkcja zwijaka - ma wlasciwie zawsze tylko 4 pola liczbowe aktualnie"""
        with st.expander("Zakres osi (puste = automatycznie)"):  # panel zwijany
            c1, c2, c3, c4 = st.columns(cols)
            x_min = c1.number_input("X od", value=None, key=f"{key_prefix}_xmin", placeholder="auto")
            x_max = c2.number_input("X do", value=None, key=f"{key_prefix}_xmax", placeholder="auto")
            y_min = c3.number_input("Y od", value=None, key=f"{key_prefix}_ymin", placeholder="auto")
            y_max = c4.number_input("Y do", value=None, key=f"{key_prefix}_ymax", placeholder="auto")
        return x_min, x_max, y_min, y_max
