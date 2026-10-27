"""Buduje wszystkie warianty modeli i porównuje je na zbiorze testowym.
Uruchom:  python main.py model                      (wszystkie warianty)
          python main.py model --warianty xgb_opad_przeszly,naiwny_tydzien"""
import argparse
import time

import pandas as pd

from .cechy import zbuduj, podziel, dopasuj
from .config import H, PODZIAL, WALIDACJA, WYNIKI
from .dane import wczytaj
from .modele import trenuj_i_prognozuj
from .ocena import metryki, wykres_obiektu, wykres_waznosci

BAZA = ["kalendarz", "lagi", "obiekt"]
POGODA = ["opad_przeszly", "pogoda_przeszla"]
RY = ["RY_PNB1", "RY_PZ1"]
WARIANTY = {
    # --- punkty odniesienia
    "naiwny_doba":              dict(typ="baseline", kolumna="b_naiwny_doba"),
    "naiwny_tydzien":           dict(typ="baseline", kolumna="b_naiwny_tydzien"),
    "profil_4tyg":              dict(typ="baseline", kolumna="b_profil_4tyg"),
    # --- model klasyczny
    "liniowy":                  dict(typ="ridge", grupy=BAZA + ["opad_przeszly"]),
    # --- XGBoost: co dają kolejne grupy danych (tylko to, co znane w chwili prognozy)
    "xgb_kalendarz_lagi":       dict(typ="xgb", grupy=BAZA),
    "xgb_opad_przeszly":        dict(typ="xgb", grupy=BAZA + ["opad_przeszly"]),
    "xgb_pogoda_przeszla":      dict(typ="xgb", grupy=BAZA + POGODA),
    "xgb_operacyjne":           dict(typ="xgb", grupy=BAZA + POGODA + ["operacyjne", "statyczne"]),
    "xgb_prognoza_pogody":      dict(typ="xgb", grupy=BAZA + POGODA + ["pogoda_prognoza"]),
    # --- krótsze okno normalizacji (7 dni zamiast 28) – szybciej łapie zmiany poziomu zużycia
    "xgb_kalendarz_lagi_7d":    dict(typ="xgb", grupy=BAZA, okno=168),
    "xgb_operacyjne_7d":        dict(typ="xgb", grupy=BAZA + POGODA + ["operacyjne", "statyczne"], okno=168),
    "xgb_prognoza_pogody_7d":   dict(typ="xgb", grupy=BAZA + POGODA + ["pogoda_prognoza"], okno=168),
    # --- osobny model dla każdego obiektu vs jeden wspólny
    "xgb_per_obiekt":           dict(typ="xgb", grupy=BAZA + POGODA, per_obiekt=True),
    # --- górna granica: pogoda zmierzona w godzinie prognozy („idealna prognoza pogody”)
    "xgb_pogoda_rzeczywista":   dict(typ="xgb", grupy=BAZA + ["opad_przeszly", "opad_rzeczywisty", "pogoda_rzeczywista"],
                                     wybor=False),
    # --- przenośność: uczony bez Rybnika, testowany na Rybniku
    "xgb_transfer_RY":          dict(typ="xgb", grupy=["kalendarz", "lagi"] + POGODA + ["statyczne"],
                                     trening_obiekty=["CH_T", "RU_W", "RU_ZMP"], test_obiekty=RY, wybor=False),
    "xgb_transfer_RY_prognoza": dict(typ="xgb", grupy=["kalendarz", "lagi"] + POGODA + ["pogoda_prognoza", "statyczne"],
                                     trening_obiekty=["CH_T", "RU_W", "RU_ZMP"], test_obiekty=RY, wybor=False),
}
# wybor=False: wariant nie bierze udziału w wyborze per obiekt (górna granica albo inny scenariusz)


def opis_podzialu(f):
    w = f.groupby(["obiekt_id", "zbior"])["czas"].agg(["min", "max", "count"]).unstack("zbior")
    print("\n== Podział (chronologicznie per obiekt)")
    for oid, r in w.iterrows():
        print(f"  {oid:8s} trening {r[('min', 'trening')]:%Y-%m-%d} → {r[('max', 'walidacja')]:%Y-%m-%d} "
              f"({r[('count', 'trening')] + r[('count', 'walidacja')]:,} h) | test {r[('min', 'test')]:%Y-%m-%d} → "
              f"{r[('max', 'test')]:%Y-%m-%d} ({r[('count', 'test')]:,} h)")


def wybor_per_obiekt(f, prog_wal, prog_test, kandydaci):
    """Dla każdego obiektu wybiera wariant z najmniejszym WAPE dobowym NA WALIDACJI i bierze jego prognozę testową."""
    wal = f[f["zbior"] == "walidacja"]
    m = pd.DataFrame([w for k in kandydaci for w in metryki(wal, prog_wal[k], k)])
    m = m[m["obiekt"] != "RAZEM"].dropna(subset=["WAPE_doba"])
    najlepszy = m.loc[m.groupby("obiekt")["WAPE_doba"].idxmin(), ["obiekt", "wariant", "WAPE_doba"]]
    wybor = dict(zip(najlepszy["obiekt"], najlepszy["wariant"]))
    pred = pd.Series(float("nan"), index=prog_test.index)
    for oid, war in wybor.items():
        maska = prog_test["obiekt_id"] == oid
        pred[maska] = prog_test.loc[maska, war]
    return pred, najlepszy.rename(columns={"WAPE_doba": "WAPE_doba_walidacja"})


def main(argv=None, d=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--warianty", default=",".join(WARIANTY))
    args = ap.parse_args(argv)
    wybrane = [w.strip() for w in args.warianty.split(",") if w.strip()]
    WYNIKI.mkdir(parents=True, exist_ok=True)

    print(f"Horyzont prognozy: {H} h | podział {PODZIAL:.0%} / {1 - PODZIAL:.0%}")
    d = d or wczytaj()
    ramki = {672: podziel(zbuduj(d, 672), PODZIAL, WALIDACJA)}
    for okno in {WARIANTY[w].get("okno", 672) for w in wybrane} - {672}:
        ramki[okno] = dopasuj(ramki[672], zbuduj(d, okno))       # ten sam podział, inne okno normalizacji
    f = ramki[672]
    opis_podzialu(f)
    test, wal = f[f["zbior"] == "test"], f[f["zbior"] == "walidacja"]
    prog = test[["czas", "obiekt_id", "kwh"]].copy()
    prog_wal = wal[["czas", "obiekt_id", "kwh"]].copy()

    wyniki = []
    print("\n== Warianty")
    for nazwa in wybrane:
        t = time.time()
        war = WARIANTY[nazwa]
        pred, pred_wal, waz, info = trenuj_i_prognozuj(ramki[war.get("okno", 672)], war)
        prog[nazwa], prog_wal[nazwa] = pred.clip(lower=0), pred_wal.clip(lower=0)
        wyniki += metryki(test, pred, nazwa)
        if waz is not None:
            waz.to_csv(WYNIKI / f"waznosc_{nazwa}.csv", header=["waznosc"])
            wykres_waznosci(waz, nazwa, WYNIKI / f"waznosc_{nazwa}.png")
        print(f"  {nazwa:26s} {time.time() - t:5.1f} s  {info}")

    kandydaci = [w for w in wybrane if WARIANTY[w].get("wybor", True)]
    if len(kandydaci) > 1:
        prog["wybor_per_obiekt"], wybor = wybor_per_obiekt(f, prog_wal, prog, kandydaci)
        wyniki += metryki(test, prog["wybor_per_obiekt"], "wybor_per_obiekt")
        wybor.round(2).to_csv(WYNIKI / "wybor_per_obiekt.csv", index=False)
        print("\n== Wybór wariantu per obiekt (na walidacji, nie na teście)")
        for _, r in wybor.iterrows():
            print(f"  {r['obiekt']:8s} → {r['wariant']:26s} (WAPE dobowe na walidacji {r['WAPE_doba_walidacja']:.1f}%)")

    met = pd.DataFrame(wyniki)
    naiwny = met[met["wariant"] == "naiwny_tydzien"].set_index("obiekt")["WAPE_doba"]
    met["poprawa_vs_naiwny_proc"] = 100 * (1 - met["WAPE_doba"] / met["obiekt"].map(naiwny))
    met.round(3).to_csv(WYNIKI / "metryki.csv", index=False)
    prog.to_csv(WYNIKI / "prognozy_test.csv.gz", index=False)

    kolejnosc = met[met["obiekt"] == "RAZEM"].sort_values("WAPE_doba")["wariant"]

    def tabela(kol, tytul):
        tab = met.pivot(index="wariant", columns="obiekt", values=kol)
        tab = tab[[c for c in tab if c != "RAZEM"] + ["RAZEM"]]
        print(f"\n== {tytul}")
        print(tab.loc[kolejnosc].round(1).to_string())

    tabela("WAPE_doba", "WAPE dobowe [%] na zbiorze testowym (mniej = lepiej)")
    print("  (warianty xgb_transfer_*: RAZEM liczone tylko dla Rybnika)")
    tabela("bias_proc", "Bias [%] (+ = zawyża, − = zaniża)")
    tabela("WAPE_doba_sucho", "WAPE dobowe [%] – doby suche")
    tabela("WAPE_doba_mokro", "WAPE dobowe [%] – doby mokre (opad > 1 mm)")
    for oid in sorted(test["obiekt_id"].unique()):
        wykres_obiektu(prog, met, oid, WYNIKI / f"test_{oid}.png")
    print(f"\nWyniki: {WYNIKI}")
    return met


if __name__ == "__main__":
    main()
