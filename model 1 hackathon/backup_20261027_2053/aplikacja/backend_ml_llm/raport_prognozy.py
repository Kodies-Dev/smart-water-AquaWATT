"""
Raport i pytania o PROGNOZE energii - na wzor report_generator z Detektora GUS.
Zasada ta sama: wszystkie liczby licza sie tutaj, w Pythonie. Model jezykowy dostaje gotowe fakty
i ma je tylko sformulowac w zdania - nie liczy nic sam i nie dodaje faktow spoza listy.
Zrodla faktow: zapisany model (modele/*_meta.json), wyniki eksperymentow (wyniki/metryki.csv)
i ostatnia prognoza z zakladki Prognoza.
"""

import pandas as pd

from backend_ml_llm.mistral_raport_generator import report_generator

NAZWY_WARIANTOW = {
    "naiwny_doba": "wczoraj o tej godzinie", "naiwny_tydzien": "tydzien temu", "profil_4tyg": "mediana z 4 tygodni",
    "liniowy": "regresja liniowa", "xgb_kalendarz_lagi": "XGBoost: kalendarz + historia",
    "xgb_opad_przeszly": "XGBoost + opad przeszly", "xgb_pogoda_przeszla": "XGBoost + pogoda przeszla",
    "xgb_operacyjne": "XGBoost + dane operacyjne", "xgb_prognoza_pogody": "XGBoost + prognoza pogody (model glowny)",
    "xgb_kalendarz_lagi_7d": "XGBoost: kalendarz + historia (okno 7 dni)", "xgb_operacyjne_7d": "XGBoost + operacyjne (7 dni)",
    "xgb_prognoza_pogody_7d": "XGBoost + prognoza pogody (7 dni)", "xgb_per_obiekt": "XGBoost osobno per obiekt",
    "xgb_pogoda_rzeczywista": "idealna pogoda (gorna granica)", "xgb_transfer_RY": "bez Rybnika w treningu",
    "xgb_transfer_RY_prognoza": "bez Rybnika w treningu + prognoza pogody", "wybor_per_obiekt": "wybor wariantu per obiekt",
}
GLOWNY = "xgb_prognoza_pogody"
REGULY = ["naiwny_doba", "naiwny_tydzien", "profil_4tyg"]


def nazwa(w):
    return NAZWY_WARIANTOW.get(w, w)


def fakty(meta=None, met=None, prog=None):
    """meta - opis zapisanego modelu, met - wyniki/metryki.csv, prog - (obiekt, wynik, metryki, sumy, jutro) z Prognozy."""
    l = []
    if meta:
        l += ["MODEL",
              f"Model: {nazwa(meta['wariant'])} (XGBoost, strata absolutna - celuje w mediane). Horyzont: {meta['horyzont_h']} h "
              f"(prognoza na nastepna dobe z danych znanych dobe wczesniej).",
              f"Trening: {meta['godzin']:,} godzin z pompowni {', '.join(meta['obiekty'])}, {meta['drzew']} drzew, "
              f"sredni blad dobowy (WAPE) na walidacji {meta['wape_doba_walidacja']}%."]
    if met is not None and len(met):
        r = met[met["obiekt"] == "RAZEM"].set_index("wariant")
        if GLOWNY in r.index:
            g = r.loc[GLOWNY]
            l += ["", "OCENA NA ZBIORZE TESTOWYM (ostatnie 30% czasu kazdej pompowni, model go nie widzial)",
                  f"WAPE dobowe modelu glownego: {g['WAPE_doba']:.1f}%, bias {g['bias_proc']:+.1f}%."]
            for w in REGULY:
                if w in r.index:
                    l.append(f"Prosta regula '{nazwa(w)}': WAPE {r.loc[w, 'WAPE_doba']:.1f}% "
                             f"- model ma o {100 * (1 - g['WAPE_doba'] / r.loc[w, 'WAPE_doba']):.0f}% mniejszy blad.")
            if "xgb_pogoda_rzeczywista" in r.index:
                l.append(f"Gdyby prognoza pogody byla idealna, sredni blad dobowy wynosilby "
                         f"{r.loc['xgb_pogoda_rzeczywista', 'WAPE_doba']:.1f}% zamiast {g['WAPE_doba']:.1f}% (gorna granica mozliwosci).")
            if "WAPE_doba_sucho" in g:
                l.append(f"Doby suche: WAPE {g['WAPE_doba_sucho']:.1f}%, doby z opadem > 1 mm: {g['WAPE_doba_mokro']:.1f}% "
                         f"- najwiekszy blad wystepuje w dni deszczowe.")
            po = met[(met["wariant"] == GLOWNY) & (met["obiekt"] != "RAZEM")]
            l.append("Per pompownia (WAPE dobowe): " + ", ".join(f"{o['obiekt']} {o['WAPE_doba']:.1f}%" for _, o in po.iterrows()) + ".")
        t = met[(met["wariant"] == "xgb_transfer_RY") & met["obiekt"].str.startswith("RY")]
        if len(t):
            l.append("Model uczony bez danych z Rybnika: " + ", ".join(f"{o['obiekt']} {o['WAPE_doba']:.1f}%"
                                                                      for _, o in t.iterrows()) + " - model przenosi sie na nowe pompownie.")
    if prog:
        oid, wynik, m, mies, jutro = prog
        l += ["", f"OSTATNIA PROGNOZA - {oid}"]
        if m:
            l.append(f"Backtest {m['od'][:10]} - {m['do'][:10]} ({m['godzin']:,} h, kazda doba prognozowana dzien wczesniej"
                     f"{', model trenowany bez tego okresu' if m.get('uczciwie') else ''}): WAPE dobowe {m['WAPE_doba']}%, "
                     f"godzinowe {m['WAPE_h']}%, bias {m['bias_proc']:+}%.")
            p = m.get("porownanie_WAPE_doba", {})
            for k in REGULY:
                if k in p:
                    l.append(f"Na tych samych dobach regula '{nazwa(k)}' ma WAPE {p[k]}% - model lepszy o "
                             f"{100 * (1 - p['model'] / p[k]):.0f}%.")
            if mies is not None and len(mies):
                ok = mies[mies["roznica_proc"].abs() <= 5]
                l.append(f"Sumy miesieczne: {len(ok)} z {len(mies)} miesiecy w granicach +-5%.")
                for mi, w in mies[mies["roznica_proc"].abs() > 5].iterrows():
                    l.append(f"Odstajacy miesiac {mi}: rzeczywiste {w['kwh']:,.0f} kWh, prognoza {w['prognoza']:,.0f} kWh "
                             f"({w['roznica_proc']:+.1f}%).")
        if jutro is not None and len(jutro):
            szczyt = jutro.loc[jutro["prognoza"].idxmax()]
            dolek = jutro.loc[jutro["prognoza"].idxmin()]
            l.append(f"Prognoza na {jutro['czas_lokalny'].min():%Y-%m-%d %H:%M} - {jutro['czas_lokalny'].max():%Y-%m-%d %H:%M}: "
                     f"razem {jutro['prognoza'].sum():.1f} kWh; najwiecej o {szczyt['czas_lokalny']:%H:%M} "
                     f"({szczyt['prognoza']:.1f} kWh/h), najmniej o {dolek['czas_lokalny']:%H:%M} ({dolek['prognoza']:.1f} kWh/h).")
    return "\n".join(l)


def raport(f, model="qwen3:8b"):
    prompt = ("Pisz po polsku, zwykly tekst (nie tabela, nie markdown). Jestes analitykiem przedsiebiorstwa "
              "wodociagowo-kanalizacyjnego i piszesz krotki raport o prognozie zuzycia energii przez pompownie sciekow.\n\n"
              "Ponizej sa JUZ GOTOWE, POLICZONE fakty. NIE zmieniaj zadnych liczb, dat ani nazw - tylko sformuluj je "
              "w plynne zdania. Nie dodawaj wlasnych obliczen ani faktow spoza listy.\n"
              "WAPE to sredni blad prognozy w procentach zuzycia (mniej = lepiej) - nazywaj go 'sredni blad', nie 'strata'. "
              "Nie odejmuj ani nie porownuj liczb samodzielnie - roznice sa juz podane w faktach.\n"
              "Struktura: 1) jakosc modelu w 2-3 zdaniach, 2) porownanie z prostymi regulami, 3) prognoza na kolejna dobe "
              "(jesli jest w faktach), 4) ograniczenia wynikajace wprost z faktow.\n\n"
              f"FAKTY:\n{f}")
    return report_generator.ask_mistral(prompt, model=model)


def pytanie(f, tresc, model="qwen3:8b", historia=None):
    rozmowa = "".join(f"\nWczesniejsze pytanie: {p}\nTwoja odpowiedz: {o}\n" for p, o in (historia or [])[-3:])
    prompt = ("Odpowiadasz po polsku, zwykly tekst. Jestes analitykiem i odpowiadasz na pytania o model prognozy "
              "zuzycia energii pompowni sciekow i jego wyniki.\n\nZASADY:\n"
              "- Opieraj sie WYLACZNIE na podanych faktach. Liczby sa juz policzone - nie licz nic sam.\n"
              "- Jesli odpowiedzi nie da sie ustalic z faktow, napisz wprost, ze tych danych tu nie ma. Nie zgaduj.\n"
              "- Odpowiadaj krotko i rzeczowo.\n\n"
              f"FAKTY:\n{f}\n{rozmowa}\nPYTANIE: {tresc}")
    return report_generator.ask_mistral(prompt, model=model)


def wczytaj_wyniki():
    """(meta modelu, metryki eksperymentow, prognozy testowe, waznosc cech modelu glownego) - co jest na dysku."""
    from model.config import WYNIKI
    import model.prognoza as P
    meta = None
    try:
        meta = P.wczytaj_model()[1]
    except FileNotFoundError:
        pass
    met = pd.read_csv(WYNIKI / "metryki.csv") if (WYNIKI / "metryki.csv").exists() else None
    prog = pd.read_csv(WYNIKI / "prognozy_test.csv.gz") if (WYNIKI / "prognozy_test.csv.gz").exists() else None
    p = WYNIKI / f"waznosc_{GLOWNY}.csv"
    waz = pd.read_csv(p, index_col=0)["waznosc"] if p.exists() else None
    return meta, met, prog, waz
