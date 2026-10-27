"""ETL: zmiana czasu i liczniki narastające – miejsca, które najłatwiej po cichu zepsuć."""
import numpy as np
import pandas as pd

from etl.wspolne import lokalny_na_utc, licznik_na_godziny, energia_koniec_godziny_na_utc


def test_jesienna_zmiana_czasu_w_kolejnosci_z_pliku():
    # odczyty co 15 min w UTC przez noc 27.10.2024 → etykiety lokalne z powtórzoną godziną 02:00–03:00
    utc = pd.date_range("2024-10-26 22:00", "2024-10-27 04:00", freq="15min", tz="UTC")
    lok = utc.tz_convert("Europe/Warsaw").tz_localize(None)
    assert pd.Series(lok).duplicated().any()                         # są zdublowane etykiety
    wynik = lokalny_na_utc(pd.Series(lok))
    assert wynik.is_unique and wynik.is_monotonic_increasing
    assert (pd.DatetimeIndex(wynik) == utc).all()


def test_licznik_zera_spadki_reset_przerwa():
    t = pd.date_range("2024-05-01", periods=10, freq="30min", tz="UTC")
    v = pd.Series([100, 110, 0, 120, 119, 130, 140, 5, 15, 25], dtype=float)   # zero, drobny spadek, reset licznika
    h = licznik_na_godziny(pd.Series(t), v)
    assert h.min() >= 0                                              # brak ujemnych przyrostów
    assert np.isclose(h.sum(), (140 - 100) + (25 - 5))               # suma z obu odcinków licznika
    t2 = pd.Series([pd.Timestamp("2024-05-01 00:00", tz="UTC"), pd.Timestamp("2024-05-01 05:00", tz="UTC")])
    h2 = licznik_na_godziny(t2, pd.Series([100.0, 200.0]))
    assert h2.notna().sum() == 0 or h2.dropna().sum() == 0           # przyrost po przerwie > 2 h = brak


def test_energia_koniec_godziny_jesien_200_proc():
    # RY: jesienią obie powtórzone godziny w jednym wierszu (etykieta 03:00) → podział na dwie godziny UTC
    etyk = pd.Series(pd.to_datetime(["2024-10-27 01:00", "2024-10-27 02:00", "2024-10-27 03:00", "2024-10-27 04:00"]))
    s = energia_koniec_godziny_na_utc(etyk, pd.Series([1.0, 1.0, 4.0, 1.0]))
    assert np.isclose(s.sum(), 7.0)                                  # nic nie zginęło
    assert len(s) == 5 and s.index.is_unique                         # 25-godzinna doba ma tu 5 godzin
    assert np.isclose(s.max(), 2.0)                                  # 4 kWh podzielone na pół


def test_energia_koniec_godziny_wiosna_bez_dziury():
    # wiosną godzina 02:00 nie istnieje; plik RY nie ma etykiety 03:00
    etyk = pd.Series(pd.to_datetime(["2024-03-31 01:00", "2024-03-31 02:00", "2024-03-31 04:00", "2024-03-31 05:00"]))
    s = energia_koniec_godziny_na_utc(etyk, pd.Series([1.0, 2.0, 3.0, 4.0]))
    assert np.isclose(s.sum(), 10.0) and s.index.is_unique
    assert (s.index.to_series().diff().dropna() == pd.Timedelta("1h")).all()   # ciągłe godziny UTC
