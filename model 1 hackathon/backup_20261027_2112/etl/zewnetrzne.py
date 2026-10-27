"""Dane z internetu: pogoda (Open-Meteo, archiwum ERA5) i kalendarz (święta PL + kalendarz szkolny Śląska)."""
import json

import holidays
import pandas as pd
import requests

from .config import CACHE, POGODA_OD, PROGNOZA_OD, POGODA_PUNKTY, FERIE_ZIMOWE, WAKACJE, PRZERWY_SWIATECZNE

URL = "https://archive-api.open-meteo.com/v1/archive"
URL_PROGNOZA = "https://previous-runs-api.open-meteo.com/v1/forecast"   # prognozy z poprzednich przebiegów modeli
ZMIENNE = {
    "temperature_2m": "temp_c",                   # temperatura [°C]
    "precipitation": "opad_mm",                   # opad całkowity (deszcz + śnieg) [mm]
    "rain": "deszcz_mm",                          # sam deszcz [mm]
    "snowfall": "snieg_cm",                       # opad śniegu [cm]
    "snow_depth": "pokrywa_m",                    # pokrywa śnieżna [m]
    "soil_moisture_0_to_7cm": "wilg_gleby_0_7",   # wilgotność gleby [m³/m³]
    "soil_moisture_7_to_28cm": "wilg_gleby_7_28",
    "et0_fao_evapotranspiration": "et0_mm",       # parowanie potencjalne [mm]
}


# Prognoza: kolumna w bazie -> zmienna Open-Meteo; pobieramy wersję „_previous_day1” (prognoza sprzed 24 h)
ZMIENNE_PROGNOZA = {"opad_mm": "precipitation", "deszcz_mm": "rain", "snieg_cm": "snowfall", "temp_c": "temperature_2m"}


def _pobierz_json(url, params, plik):
    """Pobiera JSON z Open-Meteo i zapisuje kopię w cache. Bez internetu bierze ostatnią kopię z cache.
    Błąd 400 (złe zapytanie, np. nieobsługiwana zmienna) jest zgłaszany dalej, a nie maskowany cache'em."""
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, params=params, timeout=180)
        r.raise_for_status()
        dane = r.json()
        plik.write_text(json.dumps(dane), encoding="utf-8")
        return dane, "pobrane"
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 400:
            raise
        blad = e
    except Exception as e:
        blad = e
    if plik.exists():
        return json.loads(plik.read_text(encoding="utf-8")), f"z cache (brak połączenia: {type(blad).__name__})"
    raise blad


def _pobierz(stacja, lat, lon, od, do):
    params = {"latitude": lat, "longitude": lon, "start_date": od, "end_date": do, "hourly": ",".join(ZMIENNE)}
    return _pobierz_json(URL, params, CACHE / f"openmeteo_{stacja}.json")


def pogoda(log):
    do = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=6)).date().isoformat()   # ERA5 ma kilkudniowe opóźnienie
    wynik = []
    for stacja, (lat, lon) in POGODA_PUNKTY.items():
        dane, skad = _pobierz(stacja, lat, lon, POGODA_OD, do)
        h = pd.DataFrame(dane["hourly"])
        h["czas"] = pd.to_datetime(h.pop("time")).dt.tz_localize("UTC")       # Open-Meteo domyślnie zwraca GMT
        h = h.rename(columns=ZMIENNE).dropna(subset=list(ZMIENNE.values()), how="all")
        h.insert(0, "stacja", stacja)
        log(f"Open-Meteo {stacja}", None, len(dane["hourly"]["time"]), len(h), f"{lat}, {lon} | {skad}")
        wynik.append(h[["stacja", "czas", *ZMIENNE.values()]])
    return pd.concat(wynik, ignore_index=True)


def prognoza(log):
    """Prognoza pogody wydana ok. 24 h przed daną godziną (Open-Meteo Previous Runs API, „_previous_day1”).
    To jest to, co realnie wiadomo w chwili prognozy na następną dobę. Jeśli któraś zmienna jest niedostępna,
    pobiera wersję minimalną (opad + temperatura)."""
    do = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=1)).date().isoformat()
    zestawy = [list(ZMIENNE_PROGNOZA), ["opad_mm", "temp_c"]]
    wynik = []
    for stacja, (lat, lon) in POGODA_PUNKTY.items():
        for kolumny in zestawy:
            zmienne = [f"{ZMIENNE_PROGNOZA[k]}_previous_day1" for k in kolumny]
            params = {"latitude": lat, "longitude": lon, "start_date": PROGNOZA_OD, "end_date": do, "hourly": ",".join(zmienne)}
            try:
                dane, skad = _pobierz_json(URL_PROGNOZA, params, CACHE / f"openmeteo_prognoza_{stacja}.json")
                break
            except requests.HTTPError:
                if kolumny == zestawy[-1]:
                    raise
        h = pd.DataFrame(dane["hourly"])
        h["czas"] = pd.to_datetime(h.pop("time")).dt.tz_localize("UTC")
        h = h.rename(columns={f"{z}_previous_day1": k for k, z in ZMIENNE_PROGNOZA.items()})
        h = h.reindex(columns=["czas", *ZMIENNE_PROGNOZA]).dropna(subset=list(ZMIENNE_PROGNOZA), how="all")
        h.insert(0, "stacja", stacja)
        log(f"Prognoza Open-Meteo {stacja}", None, len(dane["hourly"]["time"]), len(h),
            f"{lat}, {lon} | {skad} | zmienne: {', '.join(kolumny)}")
        wynik.append(h)
    return pd.concat(wynik, ignore_index=True)


DNI_PROGNOZY = 7     # Previous Runs API: prognozy wydane 1..7 dni wcześniej


def prognoza_dni(log, dni=DNI_PROGNOZY):
    """Archiwum prognoz pogody wydanych 1..dni dni przed daną godziną (previous_day1..7) – do uczciwej prognozy
    i oceny na K dni naprzód. Wiersz = (stacja, czas, dni, opad, deszcz, śnieg, temperatura)."""
    do = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=1)).date().isoformat()
    zestawy = [list(ZMIENNE_PROGNOZA), ["opad_mm", "temp_c"]]
    wynik = []
    for stacja, (lat, lon) in POGODA_PUNKTY.items():
        for kolumny in zestawy:
            zmienne = [f"{ZMIENNE_PROGNOZA[k]}_previous_day{n}" for n in range(1, dni + 1) for k in kolumny]
            params = {"latitude": lat, "longitude": lon, "start_date": PROGNOZA_OD, "end_date": do, "hourly": ",".join(zmienne)}
            try:
                dane, skad = _pobierz_json(URL_PROGNOZA, params, CACHE / f"openmeteo_prognoza{dni}dni_{stacja}.json")
                break
            except requests.HTTPError:
                if kolumny == zestawy[-1]:
                    raise
        h = pd.DataFrame(dane["hourly"])
        czas = pd.to_datetime(h.pop("time")).dt.tz_localize("UTC")
        for n in range(1, dni + 1):
            c = pd.DataFrame({"stacja": stacja, "czas": czas, "dni": n})
            for k in ZMIENNE_PROGNOZA:
                c[k] = h.get(f"{ZMIENNE_PROGNOZA[k]}_previous_day{n}")
            c = c.dropna(subset=list(ZMIENNE_PROGNOZA), how="all")
            wynik.append(c)
        log(f"Prognoza {dni} dni {stacja}", None, len(czas) * dni, sum(len(w) for w in wynik[-dni:]),
            f"{skad} | wyprzedzenie 1–{dni} dni | zmienne: {', '.join(kolumny)}")
    return pd.concat(wynik, ignore_index=True)


def _w_okresach(dni, okresy):
    m = pd.Series(False, index=dni)
    for od, do in okresy:
        m[(dni >= pd.Timestamp(od)) & (dni <= pd.Timestamp(do))] = True
    return m.values


def kalendarz(log, od="2023-01-01", do="2027-12-31"):
    """Dzień po dniu: weekend, święto (z nazwą), dzień wolny, mostek, ferie, wakacje, przerwy świąteczne."""
    dni = pd.date_range(od, do, freq="D")
    pl = holidays.Poland(years=range(dni.year.min(), dni.year.max() + 1))
    df = pd.DataFrame({"data": dni.date, "dzien_tyg": dni.day_of_week})   # 0 = poniedziałek
    df["weekend"] = df["dzien_tyg"] >= 5
    df["swieto"] = [d in pl for d in df["data"]]
    df["nazwa_swieta"] = [pl.get(d) for d in df["data"]]
    df["dzien_wolny"] = df["weekend"] | df["swieto"]
    wolny = df["dzien_wolny"]
    df["mostek"] = ~wolny & wolny.shift(1, fill_value=False) & wolny.shift(-1, fill_value=False)
    df["ferie_zimowe"] = _w_okresach(dni, FERIE_ZIMOWE)
    df["wakacje"] = _w_okresach(dni, WAKACJE)
    df["przerwa_swiateczna"] = _w_okresach(dni, PRZERWY_SWIATECZNE)
    log("kalendarz", None, len(df), len(df), f"świąt: {int(df['swieto'].sum())}, mostków: {int(df['mostek'].sum())}")
    return df


def kontrola_opadu(opad_ru, pogoda_df, nazwa="Open-Meteo"):
    """Czy opad z Open-Meteo (pomiar ERA5 albo prognoza) zgadza się z deszczomierzem w Rudzie? Korelacja dobowa i suma."""
    if opad_ru is None or pogoda_df is None or pogoda_df.empty:
        return
    om = pogoda_df[pogoda_df["stacja"] == "RU"].set_index("czas")["opad_mm"].resample("1D").sum()
    ds = opad_ru.set_index("czas")["mm"].resample("1D").sum()
    por = pd.concat({"deszczomierz": ds, "open_meteo": om}, axis=1).dropna()
    if len(por) > 30:
        print(f"\n== kontrola opadu RU ({nazwa}): {len(por)} dni | korelacja dobowa: {por.corr().iloc[0, 1]:.2f} | "
              f"suma deszczomierz {por['deszczomierz'].sum():.0f} mm vs {nazwa} {por['open_meteo'].sum():.0f} mm")
