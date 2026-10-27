"""
Podsumowanie prognozy dla klienta, ktory nie zna sie na modelach. Wszystko liczone i pisane w Pythonie
(bez modelu jezykowego) - liczby sa zawsze poprawne, a jezyk prosty. Zrodlo: ostatnia prognoza z zakladki Prognoza.
"""

import io
import re

import numpy as np
import pandas as pd

TZ = "Europe/Warsaw"


def _h(t):
    return f"{t:%H:%M}"


def pl(txt):
    """Polski przecinek dziesietny w liczbach przed % i kWh (daty zostaja z kropkami)."""
    return re.sub(r"(\d+)\.(\d+)(?=\s?(%|kWh))", r"\1,\2", txt)


def dzien_po_dniu(wynik, od=None):
    """Pelne doby z rzeczywistym zuzyciem: data, rzeczywiste, prognoza, roznica kWh i %."""
    w = wynik.dropna(subset=["rzeczywiste", "prognoza"])
    if od is not None:
        w = w[w["czas"] >= od]
    if w.empty:
        return pd.DataFrame(columns=["data", "rzeczywiste_kwh", "prognoza_kwh", "roznica_kwh", "roznica_proc"])
    g = w.assign(data=w["czas_lokalny"].dt.date).groupby("data")
    dz = g[["rzeczywiste", "prognoza"]].sum()[g["rzeczywiste"].count() >= 23]
    dz = dz.rename(columns={"rzeczywiste": "rzeczywiste_kwh", "prognoza": "prognoza_kwh"})
    dz["roznica_kwh"] = dz["prognoza_kwh"] - dz["rzeczywiste_kwh"]
    dz["roznica_proc"] = 100 * dz["roznica_kwh"] / dz["rzeczywiste_kwh"]
    return dz.reset_index()


def opad_dobowy(d, stacja):
    """Opad [mm/dobe] dla punktu pogody - zeby uczciwie powiedziec, czy w dniu duzego bledu padalo."""
    if d is None or stacja is None or "pogoda" not in d:
        return pd.Series(dtype=float)
    p = d["pogoda"][d["pogoda"]["stacja"] == stacja]
    if p.empty:
        return pd.Series(dtype=float)
    return p.groupby(pd.to_datetime(p["czas"], utc=True).dt.tz_convert(TZ).dt.date)["opad_mm"].sum()


def podsumuj(prog, opis=None, d=None):
    """prog = (obiekt, wynik, metryki, sumy_miesieczne, jutro) z zakladki Prognoza; opis = skad dane (plik, stacja)."""
    oid, wynik, met, mies, jutro = prog
    opis = opis or {}
    od = pd.Timestamp(met["od"]).tz_convert("UTC") if met else None
    dz = dzien_po_dniu(wynik, od) if met else dzien_po_dniu(wynik.iloc[0:0])
    s = dict(obiekt=oid, zrodlo=opis.get("zrodlo", "baza danych"), jutro_kwh=float(jutro["prognoza"].sum()),
             jutro_od=jutro["czas_lokalny"].min(), jutro_do=jutro["czas_lokalny"].max())
    szczyt, dolek = jutro.loc[jutro["prognoza"].idxmax()], jutro.loc[jutro["prognoza"].idxmin()]
    s.update(szczyt_godz=_h(szczyt["czas_lokalny"]), szczyt_kwh=float(szczyt["prognoza"]),
             dolek_godz=_h(dolek["czas_lokalny"]), dolek_kwh=float(dolek["prognoza"]))
    if len(dz):
        s.update(dni=len(dz), od=dz["data"].min(), do=dz["data"].max(), wape=float(met["WAPE_doba"]),
                 blad_kwh=float(dz["roznica_kwh"].abs().mean()), sr_doba_kwh=float(dz["rzeczywiste_kwh"].mean()),
                 dni_ponizej_10=int((dz["roznica_proc"].abs() < 10).sum()), bias=float(met["bias_proc"]),
                 uczciwie=bool(met.get("uczciwie")), widziane=float(met.get("widziane_w_treningu_proc", 0)))
        p = met.get("porownanie_WAPE_doba", {})
        if "naiwny_doba" in p:
            s.update(wczoraj=float(p["naiwny_doba"]), lepiej_niz_wczoraj=100 * (1 - p["model"] / p["naiwny_doba"]))
        naj = dz.loc[dz["roznica_kwh"].abs().idxmax()]
        opad = opad_dobowy(d, opis.get("stacja"))
        s.update(naj_data=naj["data"], naj_rz=float(naj["rzeczywiste_kwh"]), naj_pr=float(naj["prognoza_kwh"]),
                 naj_opad=float(opad.get(naj["data"], np.nan)) if len(opad) else np.nan)
    s["tekst"] = tekst(s)
    return s, dz


def tekst(s):
    zd = [f"Prognozowane zużycie energii pompowni **{s['obiekt']}** w okresie **{s['jutro_od']:%d.%m.%Y %H:%M} – "
          f"{s['jutro_do']:%d.%m %H:%M}** wynosi **{s['jutro_kwh']:.0f} kWh**. Szczyt przypada około godz. "
          f"{s['szczyt_godz']} ({s['szczyt_kwh']:.1f} kWh), minimum około godz. {s['dolek_godz']} ({s['dolek_kwh']:.1f} kWh)."]
    if "wape" in s:
        zd.append(f"Ocena dokładności na danych z pliku **{s['zrodlo']}** ({s['dni']} pełnych dób, "
                  f"{s['od']:%d.%m.%Y} – {s['do']:%d.%m.%Y}; prognoza dla każdej doby liczona z danych znanych dzień wcześniej): "
                  f"**średni błąd dobowy {s['wape']:.1f}% (ok. {s['blad_kwh']:.0f} kWh na dobę** przy średnim zużyciu "
                  f"{s['sr_doba_kwh']:.0f} kWh/dobę). Błąd poniżej 10% wystąpił w {s['dni_ponizej_10']} z {s['dni']} dób.")
        if "wczoraj" in s:
            if s["lepiej_niz_wczoraj"] > 2:
                zd.append(f"Metoda referencyjna „jak wczoraj” daje błąd {s['wczoraj']:.1f}% – "
                          f"model jest dokładniejszy o {s['lepiej_niz_wczoraj']:.0f}%.")
            else:
                zd.append(f"Metoda referencyjna „jak wczoraj” daje porównywalny błąd ({s['wczoraj']:.1f}%) – "
                          f"zużycie pompowni jest bardzo stabilne, więc przewaga modelu jest niewielka.")
        roz = s["naj_pr"] - s["naj_rz"]
        naj = (f"Największe odchylenie wystąpiło {s['naj_data']:%d.%m.%Y}: zużycie rzeczywiste {s['naj_rz']:.0f} kWh, "
               f"prognoza {s['naj_pr']:.0f} kWh ({'niedoszacowanie' if roz < 0 else 'przeszacowanie'} o {abs(roz):.0f} kWh).")
        if pd.notna(s.get("naj_opad")) and s["naj_opad"] >= 5:
            naj += (f" Tego dnia odnotowano opad ok. {s['naj_opad']:.0f} mm – wody opadowe zwiększają dopływ do "
                    f"kanalizacji, a intensywne opady są trudne do przewidzenia z wyprzedzeniem.")
        zd.append(naj)
        if s["bias"] < -3:
            zd.append(f"Prognoza była średnio o {abs(s['bias']):.0f}% niższa od zużycia rzeczywistego – "
                      f"przy planowaniu zakupu energii zaleca się zapas na dni deszczowe.")
        if s["widziane"] > 0 and not s["uczciwie"]:
            zd.append(f"**Uwaga:** {s['widziane']:.0f}% godzin z pliku znajdowało się w danych treningowych, więc rzeczywista "
                      f"dokładność może być niższa. Aby ocenić model na danych nieznanych, włącz w ustawieniach zaawansowanych "
                      f"opcję „Uczciwy backtest”.")
    return pl("\n\n".join(zd))


def excel(s, dz, jutro, mies, wynik):
    """Plik Excel dla klienta: Podsumowanie, Jutro (godzinowo), Dzień po dniu, Miesięcznie, Godzinowo (pełne)."""
    buf = io.BytesIO()
    pods = [("Pompownia", s["obiekt"]), ("Źródło danych", s["zrodlo"]),
            ("Prognoza – okres", f"{s['jutro_od']:%Y-%m-%d %H:%M} – {s['jutro_do']:%Y-%m-%d %H:%M}"),
            ("Prognoza – zużycie razem [kWh]", round(s["jutro_kwh"], 1)),
            ("Godzina największego zużycia", f"{s['szczyt_godz']} ({s['szczyt_kwh']:.1f} kWh)"),
            ("Godzina najmniejszego zużycia", f"{s['dolek_godz']} ({s['dolek_kwh']:.1f} kWh)")]
    if "wape" in s:
        pods += [("Sprawdzenie na danych – dni", s["dni"]),
                 ("Średni błąd dobowy [%]", round(s["wape"], 1)), ("Średni błąd dobowy [kWh]", round(s["blad_kwh"], 1)),
                 ("Dni z błędem < 10%", f"{s['dni_ponizej_10']} z {s['dni']}")]
        if "wczoraj" in s:
            pods.append(("Błąd metody „jak wczoraj” [%]", round(s["wczoraj"], 1)))
    pods.append(("Opis", s["tekst"].replace("**", "")))
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame(pods, columns=["co", "wartość"]).to_excel(xw, sheet_name="Podsumowanie", index=False)
        pd.DataFrame({"godzina": jutro["czas_lokalny"].dt.strftime("%Y-%m-%d %H:%M"),
                      "prognoza_kwh": jutro["prognoza"].round(2)}).to_excel(xw, sheet_name="Jutro godzinowo", index=False)
        if len(dz):
            dz.round(1).to_excel(xw, sheet_name="Dzień po dniu", index=False)
        if mies is not None and len(mies):
            mies.rename(columns={"kwh": "rzeczywiste_kwh", "prognoza": "prognoza_kwh"}).round(1).to_excel(xw, sheet_name="Miesięcznie")
        wynik.assign(czas=wynik["czas_lokalny"].dt.strftime("%Y-%m-%d %H:%M"))[["czas", "rzeczywiste", "prognoza"]] \
            .round(3).to_excel(xw, sheet_name="Godzinowo (pełne)", index=False)
        for ws in xw.book.worksheets:
            for kol in ws.columns:
                ws.column_dimensions[kol[0].column_letter].width = min(80, max(12, max(len(str(c.value or "")) for c in kol[:50]) + 2))
    return buf.getvalue()
