"""Buduje wszystkie warianty modeli i porównuje je na zbiorze testowym.
Uruchom:  python -m model.eksperymenty                      (wszystkie warianty)
          python -m model.eksperymenty --warianty xgb_opad_przeszly,naiwny_tydzien"""
import argparse
import time

import pandas as pd

from .cechy import zbuduj, podziel
from .config import H, PODZIAL, WALIDACJA, WYNIKI
from .dane import wczytaj
from .modele import trenuj_i_prognozuj
from .ocena import metryki, wykres_obiektu, wykres_waznosci

BAZA = ["kalendarz", "lagi", "obiekt"]
RY = ["RY_PNB1", "RY_PZ1"]
WARIANTY = {
    # --- punkty odniesienia
    "naiwny_doba":            dict(typ="baseline", kolumna="b_naiwny_doba"),
    "naiwny_tydzien":         dict(typ="baseline", kolumna="b_naiwny_tydzien"),
    "profil_4tyg":            dict(typ="baseline", kolumna="b_profil_4tyg"),
    # --- model klasyczny
    "liniowy":                dict(typ="ridge", grupy=BAZA + ["opad_przeszly"]),
    # --- XGBoost: co dają kolejne grupy danych (tylko to, co znane w chwili prognozy)
    "xgb_kalendarz_lagi":     dict(typ="xgb", grupy=BAZA),
    "xgb_opad_przeszly":      dict(typ="xgb", grupy=BAZA + ["opad_przeszly"]),
    "xgb_pogoda_przeszla":    dict(typ="xgb", grupy=BAZA + ["opad_przeszly", "pogoda_przeszla"]),
    "xgb_operacyjne":         dict(typ="xgb", grupy=BAZA + ["opad_przeszly", "pogoda_przeszla", "operacyjne", "statyczne"]),
    # --- XGBoost z prognozą pogody wydaną dzień wcześniej (realny scenariusz prognozy na następną dobę)
    "xgb_prognoza_pogody":    dict(typ="xgb", grupy=BAZA + ["opad_przeszly", "pogoda_przeszla", "pogoda_prognoza"]),
    "xgb_prognoza_pogody_kal": dict(typ="xgb", grupy=BAZA + ["opad_przeszly", "pogoda_przeszla", "pogoda_prognoza"],
                                    kalibracja=True),
    # --- XGBoost z „idealną prognozą pogody” (górna granica: ile da dobra prognoza pogody)
    "xgb_pogoda_rzeczywista": dict(typ="xgb", grupy=BAZA + ["opad_przeszly", "opad_rzeczywisty", "pogoda_rzeczywista"]),
    # --- osobny model dla każdego obiektu vs jeden wspólny
    "xgb_per_obiekt":         dict(typ="xgb", grupy=BAZA + ["opad_przeszly", "pogoda_przeszla"], per_obiekt=True),
    # --- przenośność: uczony bez Rybnika, testowany na Rybniku
    "xgb_transfer_RY":        dict(typ="xgb", grupy=["kalendarz", "lagi", "opad_przeszly", "pogoda_przeszla", "statyczne"],
                                   trening_obiekty=["CH_T", "RU_W", "RU_ZMP"], test_obiekty=RY),
    "xgb_transfer_RY_prognoza": dict(typ="xgb", grupy=["kalendarz", "lagi", "opad_przeszly", "pogoda_przeszla",
                                                        "pogoda_prognoza", "statyczne"],
                                     trening_obiekty=["CH_T", "RU_W", "RU_ZMP"], test_obiekty=RY),
}


def opis_podzialu(f):
    w = f.groupby(["obiekt_id", "zbior"])["czas"].agg(["min", "max", "count"]).unstack("zbior")
    print("\n== Podział (chronologicznie per obiekt)")
    for oid, r in w.iterrows():
        print(f"  {oid:8s} trening {r[('min', 'trening')]:%Y-%m-%d} → {r[('max', 'walidacja')]:%Y-%m-%d} "
              f"({r[('count', 'trening')] + r[('count', 'walidacja')]:,} h) | test {r[('min', 'test')]:%Y-%m-%d} → "
              f"{r[('max', 'test')]:%Y-%m-%d} ({r[('count', 'test')]:,} h)")


def main(argv=None, d=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--warianty", default=",".join(WARIANTY))
    args = ap.parse_args(argv)
    wybrane = [w.strip() for w in args.warianty.split(",") if w.strip()]
    WYNIKI.mkdir(parents=True, exist_ok=True)

    print(f"Horyzont prognozy: {H} h | podział {PODZIAL:.0%} / {1 - PODZIAL:.0%}")
    d = d or wczytaj()
    f = podziel(zbuduj(d), PODZIAL, WALIDACJA)
    opis_podzialu(f)
    test = f[f["zbior"] == "test"]
    prog = test[["czas", "obiekt_id", "kwh"]].copy()

    wyniki = []
    print("\n== Warianty")
    for nazwa in wybrane:
        t = time.time()
        pred, waz, info = trenuj_i_prognozuj(f, WARIANTY[nazwa])
        prog[nazwa] = pred.clip(lower=0)
        wyniki += metryki(test, pred, nazwa)
        if waz is not None:
            waz.to_csv(WYNIKI / f"waznosc_{nazwa}.csv", header=["waznosc"])
            wykres_waznosci(waz, nazwa, WYNIKI / f"waznosc_{nazwa}.png")
        print(f"  {nazwa:24s} {time.time() - t:5.1f} s  {info}")

    met = pd.DataFrame(wyniki)
    naiwny = met[met["wariant"] == "naiwny_tydzien"].set_index("obiekt")["WAPE_doba"]
    met["poprawa_vs_naiwny_proc"] = 100 * (1 - met["WAPE_doba"] / met["obiekt"].map(naiwny))
    met.round(3).to_csv(WYNIKI / "metryki.csv", index=False)
    prog.to_csv(WYNIKI / "prognozy_test.csv.gz", index=False)

    def tabela(kol, tytul):
        tab = met.pivot(index="wariant", columns="obiekt", values=kol)
        tab = tab[[c for c in tab if c != "RAZEM"] + ["RAZEM"]]
        print(f"\n== {tytul}")
        print(tab.loc[kolejnosc].round(1).to_string())

    kolejnosc = met[met["obiekt"] == "RAZEM"].sort_values("WAPE_doba")["wariant"]
    tabela("WAPE_doba", "WAPE dobowe [%] na zbiorze testowym (mniej = lepiej)")
    tabela("bias_proc", "Bias [%] (+ = zawyża, − = zaniża)")
    tabela("WAPE_doba_sucho", "WAPE dobowe [%] – doby suche")
    tabela("WAPE_doba_mokro", "WAPE dobowe [%] – doby mokre (opad > 1 mm)")
    for oid in sorted(test["obiekt_id"].unique()):
        wykres_obiektu(prog, met, oid, WYNIKI / f"test_{oid}.png")
    print(f"\nWyniki: {WYNIKI}")
    return met


if __name__ == "__main__":
    main()
