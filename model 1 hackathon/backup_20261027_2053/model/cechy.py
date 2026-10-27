"""Cechy modelu. Te same funkcje liczą cechy w treningu i w dniu konkursu.
Konwencja: cecha *_pr = znana w chwili prognozy (przesunięta o H), *_rz = wartość rzeczywista w godzinie prognozy
(udajemy idealną prognozę pogody – górna granica możliwości)."""
import numpy as np
import pandas as pd

from .config import H, TZ

KAL = ["dzien_wolny", "swieto", "mostek", "ferie_zimowe", "wakacje", "przerwa_swiateczna"]
GRUPY = {}  # nazwa grupy -> lista kolumn (wypełniane w zbuduj)


def _siatka(df, idx, kol):
    """Seria z tabeli (czas, kol) na pełną siatkę godzin."""
    if df is None or df.empty:
        return pd.Series(np.nan, index=idx)
    s = df.drop_duplicates("czas").set_index("czas")[kol]
    return s.reindex(idx)


def _dla_obiektu(oid, d, obiekt, okno=672, h=H):
    """h - wyprzedzenie prognozy [h]: kazda cecha z historii jest przesunieta o co najmniej h (24 = jutro, 168 = 7 dni)."""
    en = d["energia"][d["energia"]["obiekt_id"] == oid]
    idx = pd.date_range(en["czas"].min(), en["czas"].max(), freq="h", name="czas")
    y = _siatka(en, idx, "kwh")
    f = pd.DataFrame(index=idx)
    f["obiekt_id"] = oid
    f["kwh"] = y

    # --- kalendarz (zawsze znany)
    lok = idx.tz_convert(TZ)
    f["godzina"], f["dzien_tyg"], f["miesiac"] = lok.hour, lok.day_of_week, lok.month
    f["doy_sin"], f["doy_cos"] = np.sin(2 * np.pi * lok.day_of_year / 365.25), np.cos(2 * np.pi * lok.day_of_year / 365.25)
    kal = d["kalendarz"].copy()
    kal["data"] = pd.to_datetime(kal["data"]).dt.date
    kal = kal.set_index("data")
    for c in KAL:
        f[c] = pd.Series(lok.date, index=idx).map(kal[c].map({True: 1.0, False: 0.0}))

    # --- historia energii (znana z opóźnieniem H); normalizacja przez poziom obiektu z ostatnich 28 dni
    poziom = y.rolling(okno, min_periods=okno // 2).median().shift(h)     # okno: 672 h = 28 dni, 168 h = 7 dni
    f["poziom"] = poziom
    f["poziom_zmiana"] = (y.rolling(168, min_periods=84).median() / y.rolling(672, min_periods=336).median()).shift(h)
    for l in sorted({h, h + 24} | {x for x in (168, 336) if x >= h}):      # tylko lagi znane h godzin wczesniej
        f[f"kwh_l{l}"] = y.shift(l) / poziom
    f["kwh_sr24"] = y.rolling(24, min_periods=18).mean().shift(h) / poziom
    f["kwh_sr168"] = y.rolling(168, min_periods=120).mean().shift(h) / poziom
    f["kwh_max24"] = y.rolling(24, min_periods=18).max().shift(h) / poziom
    f["y"] = y / poziom
    f["y_log"] = np.log1p(y / poziom)          # cel modelu (patrz config.py)

    # --- baseline'y (w kWh)
    f["b_naiwny_doba"] = y.shift(24)
    f["b_naiwny_tydzien"] = y.shift(168)
    k0 = -(-h // 168)                                                   # profil z tygodni znanych w chwili prognozy
    f["b_profil_4tyg"] = pd.concat([y.shift(168 * k) for k in range(k0, k0 + 4)], axis=1).median(axis=1)
    f["profil_4tyg"] = f["b_profil_4tyg"] / poziom     # silna baza jako cecha – XGBoost uczy się korekty

    # --- opad: w Rudzie deszczomierz, gdzie indziej Open-Meteo dla punktu obiektu
    p = d["pogoda"][d["pogoda"]["stacja"] == obiekt["stacja_pogody"]]
    opad_om = _siatka(p, idx, "opad_mm")
    opad = _siatka(d["opad_ru"], idx, "mm").fillna(opad_om) if oid.startswith("RU") else opad_om
    for okno in [1, 3, 6, 24, 72, 168, 720]:
        s = opad.rolling(okno, min_periods=1).sum()
        f[f"opad_rz_{okno}h"] = s
        if okno >= 24:
            f[f"opad_pr_{okno}h"] = s.shift(h)

    # --- prognoza pogody wydana ~24 h wcześniej (Open-Meteo Previous Runs) – znana w chwili prognozy.
    #     Okna do 24 h kończą się w godzinie prognozy, więc w całości leżą w horyzoncie prognozy.
    pp = d.get("prognoza", pd.DataFrame(columns=["stacja", "czas"]))
    pp = pp[pp["stacja"] == obiekt["stacja_pogody"]]
    p_opad = _siatka(pp, idx, "opad_mm")
    for okno in [1, 3, 6, 24]:
        f[f"prog_opad_{okno}h"] = p_opad.rolling(okno, min_periods=1).sum()
    f["prog_temp"] = _siatka(pp, idx, "temp_c")
    f["prog_snieg24"] = _siatka(pp, idx, "snieg_cm").rolling(24, min_periods=1).sum()

    # --- pozostała pogoda
    temp, snieg, pokrywa = _siatka(p, idx, "temp_c"), _siatka(p, idx, "snieg_cm"), _siatka(p, idx, "pokrywa_m")
    rz = pd.DataFrame({
        "temp_rz": temp,
        "temp_sr24_rz": temp.rolling(24, min_periods=12).mean(),
        "pokrywa_rz": pokrywa,
        "topnienie24_rz": (pokrywa.shift(24) - pokrywa).clip(lower=0),
        "snieg72_rz": snieg.rolling(72, min_periods=1).sum(),
        "wilg07_rz": _siatka(p, idx, "wilg_gleby_0_7"),
        "wilg728_rz": _siatka(p, idx, "wilg_gleby_7_28"),
        "et0_168_rz": _siatka(p, idx, "et0_mm").rolling(168, min_periods=24).sum(),
    }, index=idx)
    f = f.join(rz).join(rz.shift(h).rename(columns=lambda c: c.replace("_rz", "_pr")))

    # --- dane operacyjne (tylko gdzie są: przepływ, praca pomp) – znane z opóźnieniem H
    m3 = _siatka(d["przeplyw"][d["przeplyw"]["obiekt_id"] == oid], idx, "m3")
    praca = _siatka(d["scada"][d["scada"]["obiekt_id"] == oid], idx, "praca_pomp_h")
    m3_poziom = m3.rolling(672, min_periods=336).median().shift(h)
    f["m3_sr24_pr"] = m3.rolling(24, min_periods=18).mean().shift(h) / m3_poziom
    f["praca24_pr"] = praca.rolling(24, min_periods=18).sum().shift(h)
    f["kwh_na_m3_pr"] = (y.rolling(168, min_periods=120).sum() / m3.rolling(168, min_periods=120).sum()).shift(h)

    # --- parametry obiektu ze schematu / szacunków
    for c in ["moc_pompy_kw", "wydajnosc_m3h", "zbiornik_m3"]:
        f[c] = pd.to_numeric(obiekt.get(c), errors="coerce")
    return f


def zbuduj(d, okno=672, h=H):
    """okno – okno mediany do normalizacji poziomu [h]: 672 (28 dni, domyślnie) albo krótsze, np. 168 (7 dni).
    h – wyprzedzenie prognozy [h]: 24 = następna doba (domyślnie), 24*K = K dni naprzód."""
    obiekty = d["obiekty"].set_index("obiekt_id")
    czesci = [_dla_obiektu(oid, d, obiekty.loc[oid], okno, h) for oid in sorted(d["energia"]["obiekt_id"].unique())]
    f = pd.concat(czesci).reset_index()
    for oid in sorted(f["obiekt_id"].unique()):
        f[f"ob_{oid}"] = (f["obiekt_id"] == oid).astype(float)

    GRUPY.clear()
    GRUPY.update({
        "kalendarz": ["godzina", "dzien_tyg", "miesiac", "doy_sin", "doy_cos", *KAL],
        "lagi": [c for c in f if c.startswith("kwh_l") or c in ("kwh_sr24", "kwh_sr168", "kwh_max24", "profil_4tyg", "poziom_zmiana")],
        "opad_przeszly": [c for c in f if c.startswith("opad_pr_")],
        "opad_rzeczywisty": [c for c in f if c.startswith("opad_rz_")],
        "pogoda_przeszla": [c for c in f if c.endswith("_pr") and c[:-3] + "_rz" in f],
        "pogoda_rzeczywista": [c for c in f if c.endswith("_rz") and not c.startswith("opad")],
        "pogoda_prognoza": [c for c in f if c.startswith("prog_")],
        "operacyjne": ["m3_sr24_pr", "praca24_pr", "kwh_na_m3_pr"],
        "obiekt": [c for c in f if c.startswith("ob_")],
        "statyczne": ["moc_pompy_kw", "wydajnosc_m3h", "zbiornik_m3"],
    })
    cechy = [c for g in GRUPY.values() for c in g]
    f[cechy] = f[cechy].astype(float)
    return f


def podziel(f, podzial, walidacja):
    """Chronologicznie per obiekt: trening / test; końcówka treningu = walidacja (early stopping)."""
    ok = f["y"].notna() & f["poziom"].notna() & f["b_profil_4tyg"].notna()
    f = f[ok].copy()
    f["zbior"] = "trening"
    for oid, g in f.groupby("obiekt_id"):
        t = g["czas"].sort_values()
        granica = t.iloc[int(len(t) * podzial)]
        granica_wal = t.iloc[int(len(t) * podzial * (1 - walidacja))]
        f.loc[g.index[g["czas"] >= granica], "zbior"] = "test"
        f.loc[g.index[(g["czas"] >= granica_wal) & (g["czas"] < granica)], "zbior"] = "walidacja"
    return f


def dopasuj(f_wzor, f_inny):
    """Ramka cech z innym oknem normalizacji, ułożona wiersz w wiersz jak f_wzor (ten sam podział i indeks)."""
    k = ["obiekt_id", "czas"]
    f = f_inny.set_index(k).reindex(pd.MultiIndex.from_frame(f_wzor[k])).reset_index()
    f.index = f_wzor.index
    f["zbior"] = f_wzor["zbior"]
    return f


def kolumny_grup(grupy):
    """Lista kolumn dla podanych grup cech (po wywołaniu zbuduj)."""
    return [c for g in grupy for c in GRUPY[g]]
