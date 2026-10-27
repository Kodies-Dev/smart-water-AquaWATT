"""
Wody przypadkowe w kanalizacji rozdzielczej – analiza na danych dobowych z bazy.

W kanalizacji rozdzielczej do pompowni powinny płynąć tylko ścieki bytowe. Wody przypadkowe (obce) to:
  * INFILTRACJA – wody gruntowe przez nieszczelne rury i studzienki: stały dopływ, widoczny jako wysoki przepływ
    w nocy (02–05), gdy domy prawie nie zrzucają ścieków; rośnie po długich opadach i roztopach,
  * DOPŁYW OPADOWY (nielegalne podłączenia rynien, odwodnień, kanalizacji deszczowej) – szybki skok przepływu
    w dniu deszczu, proporcjonalny do opadu.
Miary (reguły, niezależnie od ML):
  * baza bezdeszczowa – typowy przepływ / zużycie energii w suche dni (ten sam dzień tygodnia, ostatnie tygodnie),
  * nadwyżka = rzeczywiste − baza → udział wód przypadkowych w objętości i w energii,
  * reakcja na deszcz – nadwyżka na 1 mm opadu (regresja na dniach z opadem) i korelacja opad ↔ nadwyżka,
  * przepływ nocny w suche dni – przepływ 02–05 / średni przepływ doby.
Progi interpretacji są orientacyjne (literatura branżowa: nocny / średni ok. 0,3–0,45 dla ścieków bytowych).
"""

import re

import numpy as np
import pandas as pd

PROG_NOC = (0.45, 0.6)          # przepływ nocny / średni: < 0,45 niska infiltracja, 0,45–0,6 umiarkowana, > 0,6 wysoka
PROG_REAKCJI = (1.0, 3.0)       # nadwyżka [% bazy] na 1 mm opadu: < 1 słaby, 1–3 umiarkowany, > 3 silny dopływ opadowy
MOKRY_MM = 2.0                  # doba z opadem (do reakcji na deszcz)
SUCHY_3D_MM = 1.0               # doba sucha: opad z 3 dni < 1 mm


def dobowo(d):
    """Cechy dobowe wszystkich pompowni (przepływ, energia, baza bezdeszczowa, nadwyżki, przepływ nocny, opad)."""
    from anomalie.cechy_dobowe import dzienne_obiektu
    obiekty = d["obiekty"].set_index("obiekt_id")
    oof = pd.DataFrame(columns=["obiekt_id", "czas", "kwh_pred"])            # bez prognozy out-of-fold – szybciej
    czesci = [dzienne_obiektu(o, d, obiekty.loc[o], oof) for o in sorted(d["energia"]["obiekt_id"].unique())]
    df = pd.concat(czesci, ignore_index=True)
    df["dzien"] = pd.to_datetime(df["dzien"])
    return df


def anomalie_z_bazy():
    """Flagi anomalii z tabeli anomalie_dni (python main.py anomalie) – jeśli są."""
    try:
        from sqlalchemy import create_engine
        from model.config import DB_URL
        q = "select obiekt_id, dzien, anomalia, typ, glosy, opis from anomalie_dni"
        a = pd.read_sql(q, create_engine(DB_URL))
        a["dzien"] = pd.to_datetime(a["dzien"])
        return a
    except Exception:
        return None


def _regresja(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 10 or np.nanstd(x[m]) == 0:
        return np.nan, np.nan, np.nan
    a, b = np.polyfit(x[m], y[m], 1)
    r = float(np.corrcoef(x[m], y[m])[0, 1])
    return float(a), float(b), r


def ocena_infiltracji(noc):
    if pd.isna(noc):
        return "brak danych"
    return "wysoka" if noc > PROG_NOC[1] else ("umiarkowana" if noc > PROG_NOC[0] else "niska")


def ocena_dopływu(reakcja_proc):
    if pd.isna(reakcja_proc):
        return "brak danych"
    return "silny" if reakcja_proc > PROG_REAKCJI[1] else ("umiarkowany" if reakcja_proc > PROG_REAKCJI[0] else "słaby")


def ranking(df):
    """Jedna linia na pompownię: wody przypadkowe (objętość, gdy jest przepływomierz) i energia, infiltracja, reakcja na deszcz."""
    w = []
    for oid, g in df.groupby("obiekt_id"):
        lat = max((g["dzien"].max() - g["dzien"].min()).days / 365.25, 1 / 12)
        r = dict(obiekt=oid, dni=len(g))
        m = g.dropna(subset=["m3", "m3_baza"])
        r["przeplywomierz"] = len(m) > 30
        if r["przeplywomierz"]:
            mokre = m[m["opad_doba"] >= MOKRY_MM]
            a, _, kor = _regresja(mokre["opad_doba"].values, mokre["nadwyzka_m3"].values)
            r.update(udzial_wod_proc=100 * m["nadwyzka_m3"].clip(lower=0).sum() / m["m3"].sum(),
                     wody_m3_rok=m["nadwyzka_m3"].clip(lower=0).sum() / max(len(m) / 365.25, 1 / 12),
                     reakcja_m3_na_mm=a, korelacja_opad_m3=kor,
                     reakcja_proc_na_mm=float((100 * mokre["nadwyzka_m3"] / mokre["m3_baza"] / mokre["opad_doba"]).median())
                     if len(mokre) else np.nan,
                     noc_sucho=float(m.loc[m["opad_3d"] < SUCHY_3D_MM, "noc_udzial"].median()))
        e = g.dropna(subset=["kwh", "kwh_baza"])
        if len(e) > 30:
            mokre = e[e["opad_doba"] >= MOKRY_MM]
            a, _, kor = _regresja(mokre["opad_doba"].values, mokre["nadwyzka_kwh"].values)
            r.update(energia_wod_proc=100 * e["nadwyzka_kwh"].clip(lower=0).sum() / e["kwh"].sum(),
                     energia_wod_kwh_rok=e["nadwyzka_kwh"].clip(lower=0).sum() / max(len(e) / 365.25, 1 / 12),
                     reakcja_kwh_na_mm=a, korelacja_opad_kwh=kor,
                     reakcja_kwh_proc_na_mm=float((100 * mokre["nadwyzka_kwh"] / mokre["kwh_baza"] / mokre["opad_doba"]).median())
                     if len(mokre) else np.nan)
            if not r["przeplywomierz"]:                                     # bez przepływomierza – reakcja z energii
                r["reakcja_proc_na_mm"] = r["reakcja_kwh_proc_na_mm"]
        r["infiltracja"] = ocena_infiltracji(r.get("noc_sucho"))
        r["doplyw_opadowy"] = ocena_dopływu(r.get("reakcja_proc_na_mm"))
        w.append(r)
    return pd.DataFrame(w).sort_values("udzial_wod_proc" if "udzial_wod_proc" in pd.DataFrame(w) else "energia_wod_proc",
                                       ascending=False, na_position="last").reset_index(drop=True)


def opis(r):
    """Opis pompowni prostym językiem (z liczb rankingu)."""
    zd = []
    if r.get("przeplywomierz"):
        zd.append(f"Wody przypadkowe stanowią ok. **{r['udzial_wod_proc']:.0f}% przepompowanej objętości** "
                  f"(ok. {r['wody_m3_rok']:,.0f} m³ rocznie ponad typowy przepływ suchych dni).".replace(",", " "))
        zd.append(f"**Infiltracja: {r['infiltracja']}** – w suche dni przepływ nocny (02–05) wynosi {r['noc_sucho']:.2f} średniego "
                  f"przepływu doby" + (" (dla samych ścieków bytowych zwykle 0,3–0,45 – stały dopływ wód gruntowych przez nieszczelności)."
                                       if r["infiltracja"] != "niska" else " – w normie dla ścieków bytowych."))
        zd.append(f"**Dopływ opadowy: {r['doplyw_opadowy']}** – każdy 1 mm deszczu to średnio ok. {r['reakcja_m3_na_mm']:.0f} m³ "
                  f"więcej ścieków ({r['reakcja_proc_na_mm']:.1f}% typowego przepływu; korelacja opad ↔ nadwyżka "
                  f"{r['korelacja_opad_m3']:.2f})" + (" – to ślad podłączeń rynien lub odwodnień do kanalizacji sanitarnej."
                                                      if r["doplyw_opadowy"] != "słaby" else "."))
    else:
        zd.append("Brak przepływomierza – ocena na podstawie zużycia energii (pompy pracują proporcjonalnie do ilości ścieków).")
        if pd.notna(r.get("reakcja_proc_na_mm")):
            zd.append(f"**Dopływ opadowy: {r['doplyw_opadowy']}** – 1 mm deszczu to ok. {r['reakcja_proc_na_mm']:.1f}% więcej energii.")
    if pd.notna(r.get("energia_wod_proc")):
        zd.append(f"**Energia:** wody przypadkowe odpowiadają za ok. {r['energia_wod_proc']:.0f}% zużycia energii pompowni "
                  f"(ok. {r['energia_wod_kwh_rok']:,.0f} kWh rocznie); 1 mm deszczu ≈ {r['reakcja_kwh_na_mm']:.1f} kWh więcej "
                  f"(korelacja {r['korelacja_opad_kwh']:.2f}).".replace(",", " "))
    return re.sub(r"(?<=\d)\.(?=\d)", ",", " ".join(zd))          # polski przecinek dziesiętny


def dni_do_sprawdzenia(g, n=10):
    """Doby z największą nadwyżką: suche (podejrzenie infiltracji / awarii / zrzutu) i deszczowe (dopływ opadowy)."""
    kol = "nadwyzka_m3" if g["m3"].notna().mean() > 0.6 else "nadwyzka_kwh"
    jedn = "m³" if kol == "nadwyzka_m3" else "kWh"
    s = g.dropna(subset=[kol])
    suche = s[s["opad_3d"] < SUCHY_3D_MM].nlargest(n, kol)
    mokre = s[s["opad_doba"] >= MOKRY_MM].nlargest(n, kol)
    return suche, mokre, kol, jedn


# ============================================================ zdarzenia godzinowe: dzień, godziny, objętość

CENA_ZL_KWH = 1.0               # cena energii do kalkulacji (organizatorzy: PWiK Rybnik, stała cena 1 zł/kWh)
PROG_PROC = 25.0                # godzina z wodami przypadkowymi: nadwyżka >= 25% bazy godzinowej ...
PROG_MAD = 3.0                  # ... i >= 3 odchylenia (MAD) nadwyżki w suche godziny
MIN_GODZIN = 2                  # zdarzenie: co najmniej 2 godziny (przerwa 1 h nie dzieli zdarzenia)
OKNO_OPADU_H = 6                # opad liczony w trakcie zdarzenia i 6 h przed


def _opad_godz(d, oid, idx):
    ob = d["obiekty"].set_index("obiekt_id")
    st_ = ob.loc[oid, "stacja_pogody"] if oid in ob.index else "RY"
    p = d["pogoda"][d["pogoda"]["stacja"] == st_].drop_duplicates("czas").set_index("czas")["opad_mm"].reindex(idx)
    if oid.startswith("RU") and len(d.get("opad_ru", [])):
        p = d["opad_ru"].drop_duplicates("czas").set_index("czas")["mm"].reindex(idx).fillna(p)
    return p.fillna(0.0)


def _baza_godzinowa(seria, baza_dobowa, wolne, opad):
    """Baza godzinowa = dobowa baza bezdeszczowa × typowy udział godziny w dobie (suche doby, osobno robocze / wolne)."""
    lok = seria.index.tz_convert("Europe/Warsaw")
    dzien = pd.Series(lok.normalize().tz_localize(None), index=seria.index)
    typ = dzien.map(wolne).fillna(False).astype(bool)
    suma_dnia = seria.groupby(dzien.values).transform("sum")
    opad_72 = opad.rolling(72, min_periods=1).sum()
    sucho = (opad_72 < 1.0) & (seria.groupby(dzien.values).transform("count") >= 23)
    udzial = (seria / suma_dnia).where(sucho)
    klucz = pd.DataFrame({"typ": typ.values, "h": lok.hour}, index=seria.index)
    prof = udzial.groupby([klucz["typ"], klucz["h"]]).median()
    prof = prof / prof.groupby(level=0).transform("sum")                     # udziały w typie dnia sumują się do 1
    u = pd.Series([prof.get((t, h), 1 / 24) for t, h in zip(klucz["typ"], klucz["h"])], index=seria.index)
    return dzien.map(baza_dobowa).values * u.values, sucho


def zdarzenia_obiektu(d, dz, oid, cena=CENA_ZL_KWH):
    """Zdarzenia wód przypadkowych jednej pompowni: dzień, godziny od–do, objętość ponad bazę, opad, energia, koszt."""
    g = dz[dz["obiekt_id"] == oid].set_index("dzien")
    e = d["energia"][d["energia"]["obiekt_id"] == oid].drop_duplicates("czas").set_index("czas")["kwh"].sort_index()
    p = d["przeplyw"][d["przeplyw"]["obiekt_id"] == oid].drop_duplicates("czas").set_index("czas")["m3"].sort_index()
    kal = d["kalendarz"].assign(data=pd.to_datetime(d["kalendarz"]["data"])).set_index("data")["dzien_wolny"].astype(bool)
    przeplyw = len(p) > 24 * 30 and g["m3_baza"].notna().mean() > 0.5
    seria, baza_d, jedn = (p, g["m3_baza"], "m3") if przeplyw else (e, g["kwh_baza"], "kwh")
    idx = pd.date_range(seria.index.min(), seria.index.max(), freq="h")
    seria = seria.reindex(idx)
    opad = _opad_godz(d, oid, idx)
    baza, sucho = _baza_godzinowa(seria, baza_d, kal, opad)
    nad = seria - baza
    mad = (nad[sucho] - nad[sucho].median()).abs().median()
    flaga = (nad >= PROG_PROC / 100 * baza) & (nad >= PROG_MAD * 1.4826 * mad) & seria.notna()
    # łączenie godzin w zdarzenia (przerwa 1 h nie dzieli)
    f = flaga.astype(int)
    f = ((f + f.shift(1, fill_value=0).where(f.shift(-1, fill_value=0) == 1, 0)) > 0)
    nr = (f != f.shift()).cumsum()[f]
    kwh_baza_h = None
    if przeplyw:
        kb, _ = _baza_godzinowa(e.reindex(idx), g["kwh_baza"], kal, opad)
        kwh_baza_h = pd.Series(kb, index=idx)
    ek = e.reindex(idx)
    wiersze = []
    for _, h in nr.groupby(nr):
        t0, t1 = h.index.min(), h.index.max()
        if len(h) < MIN_GODZIN:
            continue
        objetosc = float(nad.loc[t0:t1].clip(lower=0).sum())
        if objetosc < 0.02 * float(np.nanmedian(baza_d)):
            continue
        op = opad.loc[t0 - pd.Timedelta(hours=OKNO_OPADU_H):t1]
        en = float((ek.loc[t0:t1] - (kwh_baza_h.loc[t0:t1] if kwh_baza_h is not None else pd.Series(baza, index=idx).loc[t0:t1]))
                   .clip(lower=0).sum())
        l0, l1 = t0.tz_convert("Europe/Warsaw"), (t1 + pd.Timedelta(hours=1)).tz_convert("Europe/Warsaw")
        wiersze.append(dict(obiekt=oid, dzien=l0.strftime("%Y-%m-%d"), godziny=f"{l0:%H:%M}–{l1:%H:%M}" + ("" if l0.date() == l1.date() else f" ({l1:%d.%m})"),
                            poczatek=l0.tz_localize(None), koniec=l1.tz_localize(None), czas_trwania_h=int(len(h)),
                            objetosc_m3=round(objetosc, 1) if przeplyw else np.nan, nadwyzka_kwh=round(en, 1),
                            koszt_zl=round(en * cena, 2), opad_mm=round(float(op.sum()), 1), max_opad_mm_h=round(float(op.max()), 1),
                            typ="dopływ opadowy" if op.sum() >= 1.0 else "dopływ bez opadu (infiltracja / zrzut / awaria)",
                            zrodlo="przepływomierz" if przeplyw else "energia (brak przepływomierza)"))
    return pd.DataFrame(wiersze), pd.DataFrame({"czas": idx, "wartosc": seria.values, "baza": baza, "opad_mm": opad.values,
                                                "flaga": flaga.values, "jednostka": jedn})


def zdarzenia(d, dz, cena=CENA_ZL_KWH):
    """Zdarzenia wszystkich pompowni + szeregi godzinowe (do wykresów)."""
    czesci, szeregi = [], {}
    for oid in sorted(dz["obiekt_id"].unique()):
        z, s = zdarzenia_obiektu(d, dz, oid, cena)
        czesci.append(z)
        szeregi[oid] = s
    z = pd.concat([c for c in czesci if len(c)], ignore_index=True) if any(len(c) for c in czesci) else pd.DataFrame()
    return z, szeregi


def podsumowanie_zdarzen(z):
    if z is None or z.empty:
        return pd.DataFrame()
    g = z.groupby("obiekt")
    return pd.DataFrame({"zdarzen": g.size(), "opadowych": g["typ"].apply(lambda t: (t == "dopływ opadowy").sum()),
                         "bez_opadu": g["typ"].apply(lambda t: (t != "dopływ opadowy").sum()),
                         "godzin": g["czas_trwania_h"].sum(), "objetosc_m3": g["objetosc_m3"].sum(min_count=1),
                         "nadwyzka_kwh": g["nadwyzka_kwh"].sum(), "koszt_zl": g["koszt_zl"].sum()}).reset_index()


def excel_zdarzen(z, cena=CENA_ZL_KWH):
    """Plik .xlsx: Zdarzenia (dzień, godziny, objętość...) + Podsumowanie per pompownia + Metoda."""
    import io
    buf = io.BytesIO()
    zz = z.drop(columns=["poczatek", "koniec"], errors="ignore").rename(columns={
        "obiekt": "pompownia", "dzien": "dzień", "godziny": "godziny wystąpienia", "czas_trwania_h": "czas trwania [h]",
        "objetosc_m3": "objętość ponad bazę [m³]", "nadwyzka_kwh": "nadwyżka energii [kWh]", "koszt_zl": f"koszt [zł] (przy {cena} zł/kWh)",
        "opad_mm": "opad w trakcie i 6 h przed [mm]", "max_opad_mm_h": "max opad [mm/h]", "typ": "typ", "zrodlo": "źródło"})
    metoda = pd.DataFrame({"opis": [
        "Baza bezdeszczowa: typowy przepływ (albo energia) w suche dni – ten sam dzień tygodnia, ostatnie tygodnie; godzinowo × "
        "typowy rozkład godzin suchej doby (osobno dni robocze i wolne).",
        f"Godzina z wodami przypadkowymi: nadwyżka >= {PROG_PROC:.0f}% bazy i >= {PROG_MAD:.0f} odchylenia typowe (MAD) z suchych godzin.",
        f"Zdarzenie: >= {MIN_GODZIN} kolejne godziny (przerwa 1 h nie dzieli). Objętość = suma nadwyżki ponad bazę.",
        f"Typ: dopływ opadowy, gdy w trakcie zdarzenia lub {OKNO_OPADU_H} h przed spadło >= 1 mm; inaczej dopływ bez opadu.",
        f"Koszt: nadwyżka energii ponad bazę × {cena} zł/kWh (stała cena energii – informacja organizatorów).",
        "Okres błędnej kalibracji przepływomierza RY_PZ1 (III 2024) odrzucony w ETL – zgodnie z zaleceniem organizatorów."]})
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        zz.to_excel(xw, sheet_name="Zdarzenia", index=False)
        podsumowanie_zdarzen(z).to_excel(xw, sheet_name="Podsumowanie", index=False)
        metoda.to_excel(xw, sheet_name="Metoda", index=False)
        from openpyxl.styles import Font
        for ws in xw.book.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    c.font = Font(name="Arial", bold=c.row == 1)
            for kol in ws.columns:
                ws.column_dimensions[kol[0].column_letter].width = min(90, max(10, max(len(str(c.value or "")) for c in kol[:200]) + 2))
    return buf.getvalue()


def main(argv=None):
    """python main.py zdarzenia [--cena 1.0] – zdarzenia wód przypadkowych wszystkich pompowni → wyniki/."""
    import argparse
    from model.config import WYNIKI
    from model.dane import wczytaj
    ap = argparse.ArgumentParser(prog="python main.py zdarzenia")
    ap.add_argument("--cena", type=float, default=CENA_ZL_KWH, help="cena energii [zł/kWh]")
    a = ap.parse_args(argv)
    d = wczytaj()
    dz = dobowo(d)
    r = ranking(dz)
    z, _ = zdarzenia(d, dz, a.cena)
    print("== Wody przypadkowe – ranking pompowni")
    kol = [c for c in ["obiekt", "udzial_wod_proc", "noc_sucho", "infiltracja", "reakcja_proc_na_mm", "doplyw_opadowy",
                       "energia_wod_proc", "energia_wod_kwh_rok"] if c in r]
    print(r[kol].round(2).to_string(index=False))
    print(f"\n== Zdarzenia (dzień, godziny, objętość) – razem {len(z)}")
    print(podsumowanie_zdarzen(z).round(1).to_string(index=False))
    print("\n  największe:")
    print(z.sort_values("nadwyzka_kwh", ascending=False).head(10)[["obiekt", "dzien", "godziny", "czas_trwania_h", "objetosc_m3",
                                                                      "nadwyzka_kwh", "koszt_zl", "opad_mm", "typ"]].to_string(index=False))
    WYNIKI.mkdir(parents=True, exist_ok=True)
    z.drop(columns=["poczatek", "koniec"]).to_csv(WYNIKI / "zdarzenia_wod_przypadkowych.csv", index=False, sep=";", decimal=",",
                                                   encoding="utf-8-sig")
    (WYNIKI / "zdarzenia_wod_przypadkowych.xlsx").write_bytes(excel_zdarzen(z, a.cena))
    r.round(3).to_csv(WYNIKI / "wody_przypadkowe_ranking.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig")
    print(f"\nWyniki: {WYNIKI / 'zdarzenia_wod_przypadkowych.xlsx'} (+ .csv), {WYNIKI / 'wody_przypadkowe_ranking.csv'}")
