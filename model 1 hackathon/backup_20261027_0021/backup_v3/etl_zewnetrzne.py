"""Dane z internetu: pogoda (Open-Meteo, archiwum ERA5) i kalendarz (święta PL + kalendarz szkolny Śląska)."""
import json

import holidays
import pandas as pd
import requests

from .config import CACHE, POGODA_OD, POGODA_PUNKTY, FERIE_ZIMOWE, WAKACJE, PRZERWY_SWIATECZNE

URL = "https://archive-api.open-meteo.com/v1/archive"
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


def _pobierz(stacja, lat, lon, od, do):
    """Pobiera z Open-Meteo; zapisuje kopię w cache. Bez internetu bierze ostatnią kopię z cache."""
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(URL, params={"latitude": lat, "longitude": lon, "start_date": od, "end_date": do,
                                      "hourly": ",".join(ZMIENNE)}, timeout=180)
        r.raise_for_status()
        dane = r.json()
        (CACHE / f"openmeteo_{stacja}.json").write_text(json.dumps(dane), encoding="utf-8")
        return dane, "pobrane"
    except Exception as e:
        plik = CACHE / f"openmeteo_{stacja}.json"
        if plik.exists():
            return json.loads(plik.read_text(encoding="utf-8")), f"z cache (brak połączenia: {type(e).__name__})"
        raise


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


def _w_okresach(dni, okresy):
    m = pd.Series(False, index=dni)
    for od, do in okresy:
        m[(dni >= pd.Timestamp(od)) & (dni <= pd.Timestamp(do))] = True
    return m.values


def kalendarz(log, od="2023-01-01", do="2027-12-31"):
    """Dzień po dniu: weekend, święto (z nazwą), dzień wolny, mostek, ferie, wakacje, przerwy świąteczne."""
    dni = pd.date_range(od, do, freq="D")
    pl = holidays.Poland(years=range(dni.year.min(), dni.year.max() + 1))
    df = pd.DataFrame({"data": dni.date, "dzien_tyg": dni.dayofweek})   # 0 = poniedziałek
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


def kontrola_opadu(opad_ru, pogoda_df):
    """Czy Open-Meteo zgadza się z deszczomierzem w Rudzie? Korelacja dobowa i suma."""
    if opad_ru is None or pogoda_df is None:
        return
    om = pogoda_df[pogoda_df["stacja"] == "RU"].set_index("czas")["opad_mm"].resample("1D").sum()
    ds = opad_ru.set_index("czas")["mm"].resample("1D").sum()
    por = pd.concat({"deszczomierz": ds, "open_meteo": om}, axis=1).dropna()
    if len(por) > 30:
        print(f"\n== kontrola opadu RU: {len(por)} dni | korelacja dobowa: {por.corr().iloc[0, 1]:.2f} | "
              f"suma deszczomierz {por['deszczomierz'].sum():.0f} mm vs Open-Meteo {por['open_meteo'].sum():.0f} mm")
