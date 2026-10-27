"""
Anomalie dla klienta: jeden przebieg łączy
  * REGUŁY  – zdarzenia wód przypadkowych (dzień, godziny, objętość, koszt) z godzinowej bazy bezdeszczowej,
  * ML      – nietypowe doby: zespół Isolation Forest + LOF + One-Class SVM (≥ 2 z 3) na cechach dobowych
              (nadwyżki ponad bazę, przepływ nocny, reszta prognozy energii, kWh/m³, opad, roztopy, nastawy, tryb panelowy),
              z typem anomalii i główną przyczyną.
Dane: plik z panelu (zużycie energii pompowni; wcześniejsze tygodnie, przepływ i SCADA z bazy) albo cała historia z bazy.
Wszystkie liczby i opisy liczy Python (bez modelu językowego).
"""

import re

import numpy as np
import pandas as pd

from backend_ml_llm import wody_przypadkowe as W

ODSETEK = 0.05                 # oczekiwany odsetek nietypowych dób – dobrany na alarmach tłoczni CH (python main.py anomalie)
NAZWY_CECH = {
    "residual_proc": "energia ponad prognozę modelu", "nadwyzka_kwh_proc": "energia ponad bazę bezdeszczową",
    "nadwyzka_m3_proc": "przepływ ponad bazę bezdeszczową", "noc_udzial": "przepływ nocny (infiltracja)",
    "kwh_na_m3_wzgl": "energia na m³ (sprawność pomp)", "poziom_max": "maks. poziom w zbiorniku", "praca_wzgl": "czas pracy pomp",
    "opad_doba": "opad doby", "opad_3d": "opad z 3 dni", "temp_sr": "temperatura", "topnienie_cm": "roztopy",
}


def dane_obiektu(d, oid, nowe=None):
    """Dane z bazy, w których zużycie energii pompowni oid zastępują / uzupełniają godziny z pliku."""
    if nowe is None or not len(nowe):
        return d
    e = d["energia"]
    inne, ta = e[e["obiekt_id"] != oid], e[e["obiekt_id"] == oid]
    ta = pd.concat([ta[~ta["czas"].isin(nowe["czas"])], nowe.assign(obiekt_id=oid)[["obiekt_id", "czas", "kwh"]]])
    dd = dict(d, energia=pd.concat([inne, ta], ignore_index=True))
    if oid not in set(d["obiekty"]["obiekt_id"]):                     # nowa pompownia – parametry jak średnie
        dd["obiekty"] = pd.concat([d["obiekty"], pd.DataFrame([dict(obiekt_id=oid, stacja_pogody="RY")])], ignore_index=True)
    return dd


def wykryj(d, oid, nowe=None, odsetek=ODSETEK, cena=W.CENA_ZL_KWH, stacja=None):
    """Pełny przebieg dla pompowni: (wynik dobowy z ML, zdarzenia, szereg godzinowy, meta)."""
    from anomalie.cechy_dobowe import dzienne
    from anomalie.detekcja import wykryj_wszystkie, nadaj_typy
    from anomalie.panel import dodaj_cechy_panelowe, dodaj_rodzaj
    dd = dane_obiektu(d, oid, nowe)
    if stacja and oid not in set(d["obiekty"]["obiekt_id"]):
        dd["obiekty"].loc[dd["obiekty"]["obiekt_id"] == oid, "stacja_pogody"] = stacja
    dz = dodaj_cechy_panelowe(dzienne(dd))
    wynik, uzyte = wykryj_wszystkie(dz, odsetek)
    wynik = nadaj_typy(dodaj_rodzaj(wynik))
    wynik["dzien"] = pd.to_datetime(wynik["dzien"])
    zd, szereg = W.zdarzenia_obiektu(dd, wynik, oid, cena)
    g = wynik[wynik["obiekt_id"] == oid].copy()
    if nowe is not None and len(nowe):
        lok = nowe["czas"].dt.tz_convert("Europe/Warsaw")
        od, do = pd.Timestamp(lok.min().date()), pd.Timestamp(lok.max().date())
    else:
        od, do = g["dzien"].min(), g["dzien"].max()
    g = g[(g["dzien"] >= od) & (g["dzien"] <= do)]
    if len(zd):
        zd = zd[(pd.to_datetime(zd["dzien"]) >= od) & (pd.to_datetime(zd["dzien"]) <= do)].copy()
        ml = g.set_index("dzien")[["anomalia", "typ"]]
        dni = pd.to_datetime(zd["dzien"])
        zd["ml_anomalia"] = dni.map(ml["anomalia"]).fillna(False).astype(bool).values
        zd["ml_typ"] = dni.map(ml["typ"]).where(zd["ml_anomalia"], "").values
    meta = dict(obiekt=oid, od=od, do=do, odsetek=odsetek, cena=cena, cechy=uzyte.get(oid, []),
                przeplyw=bool(g["m3"].notna().mean() > 0.5) if "m3" in g else False, z_pliku=nowe is not None and len(nowe) > 0)
    return g, zd, szereg, meta, wynik


def podsumuj(g, zd, meta):
    """Kafelki i opis prostym językiem (z liczb)."""
    ev = zd.drop_duplicates("zdarzenie") if len(zd) else zd
    s = dict(obiekt=meta["obiekt"], od=meta["od"], do=meta["do"], dob=len(g), dni_ml=int((g["anomalia"] == True).sum()),
             zdarzen=len(ev), opadowych=int((ev["typ"] == W.TYP_OPAD).sum()) if len(ev) else 0,
             po_opadach=int((ev["typ"] == W.TYP_PO).sum()) if len(ev) else 0, dni_zd=len(zd),
             objetosc=float(zd["objetosc_m3"].sum(min_count=1)) if len(zd) else np.nan,
             kwh=float(zd["nadwyzka_kwh"].sum()) if len(zd) else 0.0, koszt=float(zd["koszt_zl"].sum()) if len(zd) else 0.0,
             godzin=int(zd["czas_trwania_h"].sum()) if len(zd) else 0)
    m = g.dropna(subset=["m3", "m3_baza"]) if "m3" in g else g.iloc[0:0]
    s["udzial"] = float(100 * m["nadwyzka_m3"].clip(lower=0).sum() / m["m3"].sum()) if len(m) > 7 else np.nan
    e = g.dropna(subset=["kwh", "kwh_baza"])
    s["udzial_energii"] = float(100 * e["nadwyzka_kwh"].clip(lower=0).sum() / e["kwh"].sum()) if len(e) > 7 else np.nan
    s["noc"] = float(m.loc[m["opad_3d"] < W.SUCHY_3D_MM, "noc_udzial"].median()) if len(m) > 7 else np.nan
    typy = g.loc[g["anomalia"] == True, "typ"].value_counts()
    s["typy"] = typy.to_dict()
    zd_ = []
    zd_.append(f"W okresie **{meta['od']:%d.%m.%Y} – {meta['do']:%d.%m.%Y}** ({s['dob']} dób) w pompowni **{meta['obiekt']}** "
               f"wykryliśmy **{s['zdarzen']} zdarzeń wód przypadkowych** ({s['opadowych']} w czasie opadów, {s['po_opadach']} po opadach, "
               f"{s['zdarzen'] - s['opadowych'] - s['po_opadach']} bez opadu) – {s['dni_zd']} dni, łącznie {s['godzin']} godzin.")
    if pd.notna(s["objetosc"]):
        zd_.append(f"Ponad typowy przepływ suchych dni przepompowano **ok. {s['objetosc']:,.0f} m³** wód przypadkowych"
                   + (f" – to **{s['udzial']:.0f}% całej objętości**." if pd.notna(s["udzial"]) else "."))
    else:
        zd_.append("Brak przepływomierza – zdarzenia wyznaczone z zużycia energii (pompy pracują proporcjonalnie do ilości ścieków).")
    zd_.append(f"Pompowanie wód przypadkowych kosztowało **ok. {s['kwh']:,.0f} kWh ≈ {s['koszt']:,.0f} zł** (przy {meta['cena']} zł/kWh)"
               + (f"; wody przypadkowe to {s['udzial_energii']:.0f}% zużycia energii w tym okresie." if pd.notna(s["udzial_energii"]) else "."))
    if len(zd):
        naj = zd.loc[(zd["objetosc_m3"] if zd["objetosc_m3"].notna().any() else zd["nadwyzka_kwh"]).idxmax()]
        ile = f"{naj['objetosc_m3']:,.0f} m³" if pd.notna(naj["objetosc_m3"]) else f"{naj['nadwyzka_kwh']:,.0f} kWh"
        zd_.append(f"Największe zdarzenie: **{pd.Timestamp(naj['dzien']):%d.%m.%Y}, godz. {naj['godziny']}** – {ile} ponad bazę"
                   + (f", przy opadzie {naj['opad_mm']:.0f} mm." if naj["opad_mm"] >= 1 else ", bez opadu – do sprawdzenia (infiltracja, zrzut, awaria)."))
    if pd.notna(s["noc"]):
        oc = W.ocena_infiltracji(s["noc"])
        zd_.append(f"**Infiltracja: {oc}** – w suche dni przepływ nocny to {s['noc']:.2f} średniego przepływu doby"
                   + (" (wysoki – stały dopływ wód gruntowych przez nieszczelności)." if oc != "niska" else " (w normie dla ścieków bytowych)."))
    if s["dni_ml"]:
        t = ", ".join(f"{k} ({v})" for k, v in list(typy.items())[:4])
        zd_.append(f"Modele ML (Isolation Forest + LOF + One-Class SVM) wskazały nietypowe doby: **{s['dni_ml']}** "
                   f"({100 * s['dni_ml'] / max(s['dob'], 1):.0f}% okresu) – {t}.")
    if s["opadowych"] + s["po_opadach"] > s["zdarzen"] - s["opadowych"] - s["po_opadach"]:
        zd_.append("**Wniosek:** dominuje dopływ opadowy – warto sprawdzić podłączenia rynien i odwodnień w zlewni (np. testy dymowe).")
    elif s["zdarzen"]:
        zd_.append("**Wniosek:** sporo nadwyżek bez opadu – warto sprawdzić szczelność kanałów (inspekcja TV) i nietypowe zrzuty.")
    tekst = re.sub(r"(?<=\d),(?=\d{3}\b)", " ", " ".join(zd_))          # 1,234 -> 1 234 (separator tysięcy)
    tekst = re.sub(r"(\d{2})\.(\d{2})\.(\d{4})", r"\1§\2§\3", tekst)       # daty zostają z kropkami
    s["tekst"] = re.sub(r"(?<=\d)\.(?=\d)", ",", tekst).replace("§", ".")   # 0.75 -> 0,75
    return s


def metoda(meta):
    """Opis metody do raportu i zakładki szczegółów."""
    cechy = ", ".join(NAZWY_CECH.get(c, c) for c in meta.get("cechy", [])[:12])
    return [
        "DANE: zużycie energii (plik z panelu albo baza), przepływ ścieków i SCADA z bazy (gdzie są), opad (Ruda: deszczomierz, "
        "pozostałe: Open-Meteo ERA5), kalendarz. Okres błędnej kalibracji przepływomierza RY_PZ1 (III 2024) odrzucony.",
        "BAZA BEZDESZCZOWA: typowy przepływ / zużycie energii w suche dni (ten sam dzień tygodnia, ostatnie tygodnie); godzinowo – "
        "× typowy rozkład godzin suchej doby (osobno dni robocze i wolne).",
        f"ZDARZENIA (reguły): godzina z nadwyżką >= {W.PROG_PROC:.0f}% bazy i >= {W.PROG_MAD:.0f} odchylenia typowe z suchych godzin; "
        f">= {W.MIN_GODZIN} kolejne godziny = zdarzenie; objętość = suma nadwyżki; typ „dopływ opadowy”, gdy >= 1 mm opadu w trakcie "
        f"lub {W.OKNO_OPADU_H} h przed, „po opadach” – do {W.OKNO_PO_OPADZIE_H} h po deszczu; porównanie na średniej kroczącej "
        f"{W.WYGLADZENIE_H} h (cykle pomp). Wiersz = dzień zdarzenia. Koszt = nadwyżka energii × cena.",
        f"NIETYPOWE DOBY (ML): Isolation Forest + LOF + One-Class SVM osobno dla pompowni, doba nietypowa przy >= 2 głosach z 3; "
        f"oczekiwany odsetek {meta['odsetek']:.0%} (dobrany na alarmach tłoczni Chorzów). Cechy: {cechy}. Tryb panelowy: nagła zmiana "
        "względem własnej historii i odstawanie od innych pompowni tego samego dnia. Typ i główna przyczyna – reguły na cechach.",
        f"INFILTRACJA: przepływ nocny (02–05) / średni w suche dni: < {W.PROG_NOC[0]} niska, do {W.PROG_NOC[1]} umiarkowana, wyżej wysoka.",
        "WALIDACJA: alarmy tłoczni Chorzów (wskazania ~2,6× częściej przy alarmach niż losowo), powódź IX 2024 wykryta na 4/4 "
        "pompowniach jako dopływ opadowy (python main.py anomalie).",
    ]
