"""Wczytanie tabel z bazy po ETL."""
import pandas as pd
from sqlalchemy import create_engine

from .config import DB_URL


def _albo_puste(q, sql, kolumny):
    """Tabela może nie istnieć (stara baza bez prognoz) – wtedy pusta ramka, a warianty z prognozą działają jak bez niej."""
    try:
        return q(sql)
    except Exception:
        return pd.DataFrame(columns=kolumny)


def wczytaj():
    e = create_engine(DB_URL)
    q = lambda sql: pd.read_sql(sql, e)
    d = {
        "energia": q("select obiekt_id, czas, kwh from energia_godz"),
        "przeplyw": q("select obiekt_id, czas, m3 from przeplyw_godz"),
        "scada": q("select obiekt_id, czas, praca_pomp_h, poziom_max, prog_start, prog_stop from scada_godz"),
        "opad_ru": q("select czas, mm from opad_godz where stacja = 'RU'"),
        "pogoda": q("select * from pogoda_godz"),
        "prognoza": _albo_puste(q, "select * from prognoza_pogody_godz", ["stacja", "czas", "opad_mm", "deszcz_mm", "snieg_cm", "temp_c"]),
        "kalendarz": q("select * from kalendarz"),
        "obiekty": q("select * from obiekty"),
    }
    for k, df in d.items():
        if "czas" in df:
            df["czas"] = pd.to_datetime(df["czas"], utc=True)
    return d
