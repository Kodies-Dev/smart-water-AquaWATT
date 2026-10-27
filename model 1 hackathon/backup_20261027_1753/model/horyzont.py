"""Jak dokładna jest prognoza na 1..7 dni naprzód – uczciwa ocena na zbiorze testowym.

    python main.py horyzont [--dni 7]

Dla każdego K: model uczony na treningu (70% czasu, early stopping na walidacji), cechy przesunięte o 24·K h,
prognoza pogody wydana K dni wcześniej (archiwum Open-Meteo) → WAPE dobowe na teście, obok proste metody:
„tak jak K dni temu” i typowy dzień z 4 tygodni znanych w chwili prognozy.
Wynik: wyniki/horyzont.csv, wyniki/horyzont.png (do zakładki Model i na slajd).
"""
import argparse
import time

import numpy as np
import pandas as pd
import xgboost as xgb

from .cechy import zbuduj, podziel, kolumny_grup
from .config import PODZIAL, WALIDACJA, TZ, WYNIKI
from .prognoza import dla_dni, GRUPY_MODELU, MODELE

TYDZIEN = 7


def _wape(df, kol):
    d = df.dropna(subset=["kwh", kol]).assign(dzien=lambda x: x["czas"].dt.tz_convert(TZ).dt.date)
    g = d.groupby(["obiekt_id", "dzien"])
    s = g[["kwh", kol]].sum()[g["kwh"].count() >= 23]
    return float(100 * (s[kol] - s["kwh"]).abs().sum() / s["kwh"].sum()) if len(s) else np.nan


def ocen_dni(d, k):
    from .strojenie import parametry_modelu
    f = podziel(zbuduj(dla_dni(d, k), h=24 * k), PODZIAL, WALIDACJA)
    X = kolumny_grup(GRUPY_MODELU)
    tr, wal, te = (f[f["zbior"] == z] for z in ("trening", "walidacja", "test"))
    params, _ = parametry_modelu(MODELE)
    m = xgb.XGBRegressor(**params, n_estimators=3000, early_stopping_rounds=200)
    m.fit(tr[X], tr["y_log"], eval_set=[(wal[X], wal["y_log"])], verbose=False)
    te = te.assign(model=np.expm1(np.clip(m.predict(te[X]), 0, None)) * te["poziom"].values)
    # „tak jak K dni temu”: zużycie tej samej godziny K dni wcześniej (z pełnej serii, nie tylko z testu)
    pelne = f.set_index(["obiekt_id", "czas"])["kwh"]
    klucz = pd.MultiIndex.from_arrays([te["obiekt_id"], te["czas"] - pd.Timedelta(hours=24 * k)])
    te["jak_k_dni_temu"] = pelne.reindex(klucz).values
    wiersze = []
    for oid, g in [*te.groupby("obiekt_id"), ("RAZEM", te)]:
        wiersze.append(dict(dni=k, obiekt=oid, model=_wape(g, "model"), jak_k_dni_temu=_wape(g, "jak_k_dni_temu"),
                            profil_4tyg=_wape(g, "b_profil_4tyg"), drzew=m.best_iteration + 1))
    return wiersze


def wykres(t, sciezka):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    r = t[t["obiekt"] == "RAZEM"].set_index("dni")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(r.index, r["model"], marker="o", lw=2, color="#C00000", label="nasz model")
    ax.plot(r.index, r["jak_k_dni_temu"], marker="s", lw=1.2, color="#8C8C8C", label="„tak jak K dni temu”")
    ax.plot(r.index, r["profil_4tyg"], marker="^", lw=1.2, color="#595959", label="typowy dzień z 4 tygodni")
    for x, y in r["model"].items():
        ax.annotate(f"{y:.1f}%", (x, y), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=9)
    ax.set_xlabel("ile dni naprzód"); ax.set_ylabel("średni błąd dobowy (WAPE) [%]")
    ax.set_title("Dokładność prognozy a horyzont (test: ostatnie 30% czasu każdej pompowni)")
    ax.set_xticks(r.index); ax.grid(alpha=0.3); ax.legend()
    plt.tight_layout(); plt.savefig(sciezka, dpi=110); plt.close(fig)


def main(argv=None, d=None):
    ap = argparse.ArgumentParser(prog="python main.py horyzont")
    ap.add_argument("--dni", type=int, default=TYDZIEN)
    ap.add_argument("--dlugi", action="store_true", help="ocena planu na 2 miesiące (model długoterminowy)")
    a = ap.parse_args(argv)
    if d is None:
        from .dane import wczytaj
        d = wczytaj()
    if a.dlugi:
        from .dlugi import main_ocena
        return main_ocena(d)
    if d.get("prognoza_dni") is None or d["prognoza_dni"].empty:
        print("  uwaga: brak tabeli prognoza_pogody_dni – uruchom python main.py etl (dni 2+ bez prognozy pogody)")
    wiersze = []
    print(f"== Dokładność prognozy na 1–{a.dni} dni naprzód (test)")
    for k in range(1, a.dni + 1):
        t = time.time()
        w = ocen_dni(d, k)
        wiersze += w
        r = [x for x in w if x["obiekt"] == "RAZEM"][0]
        print(f"  +{k} dni: model {r['model']:.1f}% | „jak {k} dni temu” {r['jak_k_dni_temu']:.1f}% | "
              f"typowy dzień {r['profil_4tyg']:.1f}%  ({time.time() - t:.0f} s)")
    t = pd.DataFrame(wiersze)
    WYNIKI.mkdir(parents=True, exist_ok=True)
    t.round(2).to_csv(WYNIKI / "horyzont.csv", index=False)
    wykres(t, WYNIKI / "horyzont.png")
    print("\n  per pompownia (WAPE dobowe modelu [%]):")
    print(t.pivot(index="dni", columns="obiekt", values="model").round(1).to_string())
    print(f"\nWyniki: {WYNIKI / 'horyzont.csv'}, {WYNIKI / 'horyzont.png'}")
    return t


if __name__ == "__main__":
    main()
