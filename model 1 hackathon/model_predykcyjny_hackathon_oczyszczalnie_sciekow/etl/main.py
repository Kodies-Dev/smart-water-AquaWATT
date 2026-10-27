"""ETL: surowe pliki z Dane/ -> Postgres. Uruchom:  python -m etl.main  (albo przez docker compose)."""
import time
import traceback

import pandas as pd

from . import ch, ru, ry, zewnetrzne
from .baza import polacz, przygotuj, zapisz
from .config import DANE, OBIEKTY

START = pd.Timestamp.now(tz="UTC")
LOG = []


def log(krok, obiekt_id, wej, wyj, uwagi=""):
    proc = f" ({100 * (1 - wyj / wej):.1f}% odrzucone)" if wej and wyj <= wej else ""
    print(f"  [{krok}] {obiekt_id or ''}: {wej:,} -> {wyj:,}{proc} {uwagi}")
    LOG.append(dict(uruchomienie=START, krok=krok, obiekt_id=obiekt_id, wiersze_wej=wej, wiersze_wyj=wyj, uwagi=uwagi))


def krok(nazwa, funkcja):
    """Uruchamia jeden krok; błąd w jednym źródle nie zatrzymuje całego ETL."""
    print(f"\n== {nazwa}")
    t = time.time()
    try:
        wynik = funkcja(log)
        print(f"  ok ({time.time() - t:.0f} s)")
        return wynik
    except Exception as e:
        traceback.print_exc()
        log(nazwa, None, 0, 0, f"BŁĄD: {e}")
        return None


def kontrola_faktur(energia, faktury):
    """Faktury vs suma raportów godzinowych (miesięcznie). Różnica > 1% = do sprawdzenia."""
    if energia is None or faktury is None or faktury.empty:
        return
    e = energia.copy()
    e["miesiac"] = e["czas"].dt.tz_convert("Europe/Warsaw").dt.tz_localize(None).dt.to_period("M").dt.start_time.dt.date
    suma = e.groupby(["obiekt_id", "miesiac"])["kwh"].sum().rename("raport").reset_index()
    por = faktury.merge(suma, on=["obiekt_id", "miesiac"])
    por["roznica_%"] = (por["raport"] / por["kwh"] - 1) * 100
    zle = por[por["roznica_%"].abs() > 1]
    print(f"\n== kontrola faktur: {len(por)} wspólnych miesięcy, różnica > 1%: {len(zle)}")
    if len(zle):
        print(zle.round(1).to_string(index=False))


def razem(*czesci):
    czesci = [x for x in czesci if x is not None and not x.empty]
    return pd.concat(czesci, ignore_index=True) if czesci else None


def main():
    print(f"Dane: {DANE}")
    if not (DANE / "CH").exists():
        raise SystemExit(f"Nie ma danych w: {DANE}\nUstaw DANE_DIR albo połóż folder Dane obok programu.")
    engine = polacz()
    przygotuj(engine)
    zapisz(engine, pd.DataFrame(OBIEKTY), "obiekty")

    en_ch = krok("CH energia", ch.energia)
    pr_ch = krok("CH przepływ", ch.przeplyw)
    al_ch = krok("CH alarmy", ch.alarmy)
    en_ru = krok("RU energia", ru.energia)
    opad = krok("RU opad", ru.opad)
    sc_ru = krok("RU SCADA", ru.scada)
    en_ry = krok("RY energia", ry.energia)
    pr_ry = krok("RY przepływ", ry.przeplyw)
    fa_ry = krok("RY faktury", ry.faktury)
    pogoda = krok("Pogoda (Open-Meteo)", zewnetrzne.pogoda)
    prognoza = krok("Prognoza pogody z dnia poprzedniego (Open-Meteo)", zewnetrzne.prognoza)
    prognoza_dni = krok("Prognozy pogody wydane 1–7 dni wcześniej (Open-Meteo)", zewnetrzne.prognoza_dni)
    kal = krok("Kalendarz", zewnetrzne.kalendarz)

    kontrola_faktur(en_ry, fa_ry)
    zewnetrzne.kontrola_opadu(opad, pogoda, "pogoda ERA5")
    zewnetrzne.kontrola_opadu(opad, prognoza, "prognoza z dnia poprzedniego")
    if prognoza_dni is not None and len(prognoza_dni):
        for n in sorted(prognoza_dni["dni"].unique()):
            zewnetrzne.kontrola_opadu(opad, prognoza_dni[prognoza_dni["dni"] == n], f"prognoza {n} dni wcześniej")

    print("\n== zapis do bazy")
    zapisz(engine, razem(en_ch, en_ru, en_ry), "energia_godz")
    zapisz(engine, fa_ry, "energia_mies")
    zapisz(engine, razem(pr_ch, pr_ry, sc_ru[1] if sc_ru else None), "przeplyw_godz")
    zapisz(engine, sc_ru[0] if sc_ru else None, "scada_godz")
    zapisz(engine, opad, "opad_godz")
    zapisz(engine, al_ch, "alarmy")
    zapisz(engine, pogoda, "pogoda_godz")
    zapisz(engine, prognoza, "prognoza_pogody_godz")
    zapisz(engine, prognoza_dni, "prognoza_pogody_dni")
    zapisz(engine, kal, "kalendarz")
    zapisz(engine, pd.DataFrame(LOG), "etl_log")
    print(f"\nGotowe w {(pd.Timestamp.now(tz='UTC') - START).total_seconds():.0f} s")


if __name__ == "__main__":
    main()
