"""Zapis do Postgresa."""
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from .config import DB_URL

SCHEMA = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"
TABELE = ["alarmy", "kalendarz", "prognoza_pogody_godz", "pogoda_godz", "opad_godz", "scada_godz", "przeplyw_godz", "energia_mies", "energia_godz", "obiekty"]


def polacz():
    return create_engine(DB_URL)


def przygotuj(engine):
    """Tworzy tabele (jeśli nie ma) i czyści dane – ETL ładuje wszystko od zera."""
    with engine.begin() as con:
        con.execute(text(SCHEMA.read_text(encoding="utf-8")))
        con.execute(text(f"TRUNCATE {', '.join(TABELE)}"))


def zapisz(engine, df, tabela):
    if df is None or df.empty:
        print(f"  {tabela}: brak danych")
        return
    df.to_sql(tabela, engine, if_exists="append", index=False, chunksize=5000, method="multi")
    print(f"  {tabela}: +{len(df):,} wierszy")
