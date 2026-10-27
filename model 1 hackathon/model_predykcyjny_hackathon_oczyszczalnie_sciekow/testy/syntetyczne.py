"""Generator danych syntetycznych o strukturze jak w bazie po ETL (do testów bez bazy)."""
import numpy as np
import pandas as pd

from etl.zewnetrzne import kalendarz

OBIEKTY = [  # obiekt, punkt pogody, poziom kWh/h, od, do, przepływ?
    ("CH_T", "CH", 4.0, "2024-03-01", "2025-08-31", True),
    ("RU_W", "RU", 2.7, "2024-01-01", "2025-08-31", True),
    ("RY_PZ1", "RY", 11.0, "2024-01-06", "2025-06-30", True),
]


def dane(seed=7):
    rng = np.random.default_rng(seed)
    t = pd.date_range("2023-10-01", "2025-09-30", freq="h", tz="UTC")
    pogoda = []
    for st in ["CH", "RU", "RY"]:
        deszcz = np.where(rng.random(len(t)) < 0.04, rng.gamma(1.2, 1.5, len(t)), 0)
        doy = t.day_of_year.values
        pogoda.append(pd.DataFrame({"stacja": st, "czas": t, "temp_c": 8 - 10 * np.cos(2 * np.pi * doy / 365) + rng.normal(0, 3, len(t)),
                                    "opad_mm": deszcz, "deszcz_mm": deszcz, "snieg_cm": 0.0, "pokrywa_m": 0.0,
                                    "wilg_gleby_0_7": 0.3, "wilg_gleby_7_28": 0.3, "et0_mm": 0.1}))
    pogoda = pd.concat(pogoda, ignore_index=True)
    kal = kalendarz(lambda *a: None)
    wolne = set(pd.to_datetime(kal.loc[kal["dzien_wolny"], "data"]).dt.date)
    obiekty = pd.DataFrame([dict(obiekt_id=o, stacja_pogody=s, moc_pompy_kw=None, wydajnosc_m3h=None, zbiornik_m3=None)
                            for o, s, *_ in OBIEKTY])
    en, prz, sc = [], [], []
    for o, st, base, od, do, ma_przeplyw in OBIEKTY:
        tt = pd.date_range(od, do, freq="h", tz="UTC")
        r = pogoda[pogoda["stacja"] == st].set_index("czas")["opad_mm"]
        szybki = r.rolling(6, min_periods=1).sum().reindex(tt).values
        wolny = r.rolling(168, min_periods=1).sum().reindex(tt).values
        lok = tt.tz_convert("Europe/Warsaw")
        dob = 1 + 0.35 * np.sin(2 * np.pi * (lok.hour - 7) / 24)
        wd = np.array([0.88 if x in wolne else 1.0 for x in lok.date])
        sezon = 1 + 0.15 * np.cos(2 * np.pi * lok.day_of_year / 365)
        kwh = base * dob * wd * sezon * (1 + 0.08 * szybki + 0.01 * wolny) * rng.lognormal(0, 0.10, len(tt))
        en.append(pd.DataFrame({"obiekt_id": o, "czas": tt, "kwh": kwh}))
        if ma_przeplyw:
            prz.append(pd.DataFrame({"obiekt_id": o, "czas": tt, "m3": kwh / 0.2 * rng.lognormal(0, 0.04, len(tt))}))
        if o.startswith("RU"):
            sc.append(pd.DataFrame({"obiekt_id": o, "czas": tt, "praca_pomp_h": kwh / 5, "poziom_max": 140.0}))
    prog = pogoda[["stacja", "czas", "opad_mm", "deszcz_mm", "snieg_cm", "temp_c"]].copy()
    prog["opad_mm"] = prog.groupby("stacja")["opad_mm"].shift(1).fillna(0) * rng.uniform(0.5, 1.5, len(prog))
    # archiwum prognoz wydanych 1..7 dni wcześniej: im dalej, tym większy błąd
    dni = []
    for n in range(1, 8):
        p = pogoda[["stacja", "czas", "opad_mm", "deszcz_mm", "snieg_cm", "temp_c"]].copy()
        p["opad_mm"] = p["opad_mm"] * rng.uniform(1 - 0.12 * n, 1 + 0.12 * n, len(p)).clip(0)
        p["temp_c"] = p["temp_c"] + rng.normal(0, 0.5 * n, len(p))
        dni.append(p.assign(dni=n))
    prognoza_dni = pd.concat(dni, ignore_index=True)
    return dict(energia=pd.concat(en, ignore_index=True), przeplyw=pd.concat(prz, ignore_index=True),
                scada=pd.concat(sc, ignore_index=True),
                opad_ru=pogoda[pogoda["stacja"] == "RU"][["czas", "opad_mm"]].rename(columns={"opad_mm": "mm"}),
                pogoda=pogoda, prognoza=prog, prognoza_dni=prognoza_dni, kalendarz=kal, obiekty=obiekty)
