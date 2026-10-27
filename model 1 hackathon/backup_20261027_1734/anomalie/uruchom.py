"""Wykrywanie anomalii. Uruchom:  python main.py anomalie"""
import time

import pandas as pd

from etl.baza import polacz
from model.dane import wczytaj
from .cechy_dobowe import dzienne
from .panel import dodaj_cechy_panelowe, dodaj_rodzaj
from .ustawienia import WYNIKI, ODSETKI, ODSETEK_DOMYSLNY, MIN_ZLAPANE_PROC
from .detekcja import wykryj_wszystkie, nadaj_typy
from .ocena_anomalii import (dni_alarmow, walidacja_ch, znane_zdarzenia, ranking, wykres_obiektu, wykres_rankingu,
                             przyczyny, wykres_przyczyn)


def wczytaj_alarmy():
    try:
        return pd.read_sql("select obiekt_id, czas, sygnal, stan from alarmy", polacz())
    except Exception:
        return pd.DataFrame(columns=["obiekt_id", "czas", "sygnal", "stan"])


def dobierz_odsetek(dz, alarmy_dni):
    """Sprawdza ODSETKI na alarmach CH. Wybór: najwyższy lift zespołu (ile razy częściej niż losowo wskazuje doby przy
    alarmach) spośród odsetków, które łapią >= MIN_ZLAPANE_PROC% dni z alarmem; remis -> mniejszy odsetek (mniej dób do
    przejrzenia). Kryterium F1 rosło razem z odsetkiem (alarmów w CH jest dużo), więc wybierało skraj siatki.
    Zwraca (odsetek, tabela walidacji, uzasadnienie). Używane też przez aplikację Streamlit."""
    walid = [walidacja_ch(wykryj_wszystkie(dz, o)[0], alarmy_dni, o) for o in ODSETKI] if alarmy_dni else []
    walid = pd.concat(walid, ignore_index=True) if any(len(w) for w in walid) else pd.DataFrame()
    if walid.empty:
        return ODSETEK_DOMYSLNY, walid, "brak alarmów do walidacji – domyślny"
    z = walid[walid["model"].str.startswith("zespół")].copy()
    ok = z[(z["zlapane_wszystkie_proc"] >= MIN_ZLAPANE_PROC) & z["lift"].notna()]
    if len(ok):
        w = ok.sort_values(["lift", "odsetek"], ascending=[False, True]).iloc[0]
        return (float(w["odsetek"]), walid, f"najwyższy lift ({w['lift']:.1f}×) przy złapanych >= {MIN_ZLAPANE_PROC}% "
                                            f"dni z alarmem ({w['zlapane_wszystkie_proc']:.0f}%)")
    if z["lift"].notna().any():
        w = z.sort_values(["zlapane_wszystkie_proc", "lift"], ascending=False).iloc[0]
        return float(w["odsetek"]), walid, f"żaden nie łapie {MIN_ZLAPANE_PROC}% alarmów – najwięcej złapanych"
    return ODSETEK_DOMYSLNY, walid, "żaden odsetek nie złapał alarmów – domyślny"


def main(argv=None, d=None, alarmy=None, zapis_do_bazy=True):
    WYNIKI.mkdir(parents=True, exist_ok=True)
    t = time.time()
    d = d or wczytaj()
    alarmy = wczytaj_alarmy() if alarmy is None else alarmy
    print("== Cechy dobowe (z prognozą energii out-of-fold)")
    dz = dodaj_cechy_panelowe(dzienne(d))          # + tryb panelowy z Detektora Anomalii (jump_score, zscore_miedzy, IQR)
    print(f"  {len(dz):,} dób, {dz['obiekt_id'].nunique()} obiekty ({time.time() - t:.0f} s)")

    # --- dobór „oczekiwanego odsetka anomalii” na alarmach CH
    alarmy_dni = dni_alarmow(alarmy)
    odsetek, walid, powod = dobierz_odsetek(dz, alarmy_dni)
    if len(walid):
        walid.round(2).to_csv(WYNIKI / "walidacja_CH.csv", index=False)
        print("\n== Walidacja na alarmach tłoczni CH (±1 doba)")
        kol = ["odsetek", "model", "wskazanych_dni", "zlapane_wszystkie_proc", "trafienia_przy_alarmie_proc", "lift"]
        kol += [c for c in walid if c.startswith("zlapane_") and c != "zlapane_wszystkie_proc"]
        pokaz = walid[kol].round(1).assign(odsetek=walid["odsetek"].map("{:.0%}".format))
        print(pokaz.to_string(index=False))
    print(f"\n  wybrany odsetek: {odsetek:.0%} ({powod})")

    # --- wynik końcowy
    wynik, uzyte = wykryj_wszystkie(dz, odsetek)
    wynik = nadaj_typy(dodaj_rodzaj(wynik))
    print("\n== Cechy użyte per obiekt")
    for oid, cols in uzyte.items():
        print(f"  {oid:8s} {', '.join(cols)}")

    rank = ranking(wynik)
    zn = znane_zdarzenia(wynik)
    anom = wynik[wynik["anomalia"] == True].sort_values(["obiekt_id", "dzien"])
    wynik.to_csv(WYNIKI / "dni.csv", index=False)
    anom.to_csv(WYNIKI / "anomalie.csv", index=False)
    rank.round(2).to_csv(WYNIKI / "ranking.csv", index=False)
    zn.to_csv(WYNIKI / "znane_zdarzenia.csv", index=False)
    for oid in sorted(wynik["obiekt_id"].unique()):
        wykres_obiektu(wynik, oid, WYNIKI / f"anomalie_{oid}.png", alarmy_dni)
    wykres_rankingu(rank, WYNIKI / "ranking.png")
    licz, roz, per_typ = przyczyny(wynik)
    if len(licz):
        licz.round(2).to_csv(WYNIKI / "przyczyny.csv")
        roz.round(2).to_csv(WYNIKI / "przyczyny_rozroznianie.csv")
        per_typ.to_csv(WYNIKI / "przyczyny_per_typ.csv")
        wykres_przyczyn(licz, roz, WYNIKI / "przyczyny.png")

    print("\n== Anomalie per obiekt i typ")
    print(anom.groupby(["obiekt_id", "typ"]).size().unstack(fill_value=0).to_string())
    print("\n== Rodzaj anomalii (tryb panelowy: własna historia vs inne pompownie tego samego dnia)")
    print(anom.groupby(["obiekt_id", "Rodzaj_Anomalii"]).size().unstack(fill_value=0).to_string())
    print("\n== Ranking obiektów")
    kol = [c for c in ["obiekt", "dni", "anomalii", "udzial_wod_obcych_proc", "reakcja_m3_na_mm", "noc_udzial_sucho",
                       "nadwyzka_energii_proc", "reakcja_kwh_na_mm"] if c in rank]
    print(rank[kol].round(2).to_string(index=False))
    if len(licz):
        print("\n== Co wyróżnia anomalie (główna przyczyna)")
        print(licz[["nazwa", "anomalii", "udzial_proc"]].round(1).to_string())
        print("\n== Przykłady (największe anomalie)")
        top = anom.assign(s=anom["skala_m3"].abs().fillna(anom["skala_kwh"].abs())).sort_values("s", ascending=False)
        for o in top["opis"].head(5):
            print("  " + o)
    print("\n== Znane zdarzenia")
    print(zn.to_string(index=False) if len(zn) else "  brak w danych")

    if zapis_do_bazy:
        try:
            kol = ["obiekt_id", "dzien", "IF", "LOF", "SVM", "glosy", "anomalia", "typ", "Rodzaj_Anomalii", "glowna_cecha",
                   "z_glownej", "Nagla_Zmiana", "Odstaje_Od_Innych", "Has_Outlier", "skala_m3", "skala_kwh",
                   "nadwyzka_m3_proc", "residual_proc", "opad_doba", "opis"]
            wynik[kol].to_sql("anomalie_dni", polacz(), if_exists="replace", index=False, chunksize=5000, method="multi")
            print("\n  zapisano tabelę anomalie_dni w bazie")
        except Exception as e:
            print(f"\n  nie zapisano do bazy: {e}")
    print(f"\nWyniki: {WYNIKI} ({time.time() - t:.0f} s)")
    return wynik


if __name__ == "__main__":
    main()
