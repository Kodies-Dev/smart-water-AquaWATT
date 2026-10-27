"""
Raport w Excelu z najważniejszymi wykresami – jeden plik dla klienta.

Arkusze (te, dla których są dane): Podsumowanie · Jutro godzinowo · Dzień po dniu · Miesięcznie · Tydzień ·
Plan 2 miesiące · Pogoda · Raport AI · Godzinowo. Wykresy są natywne (edytowalne w Excelu), a sumy, różnice i błędy
liczą się FORMUŁAMI z arkuszy z danymi - zmiana danych przelicza raport. Wartości spoza pliku (np. błąd metody
„jak wczoraj” z backtestu) są opisane w komórce obok.
"""

import io
from datetime import datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FONT = "Arial"
GRANAT, CZERWONY, SZARY, ZIELONY, NIEBIESKI = "1F4E79", "C00000", "8C8C8C", "217346", "2E75B6"
CIENKA = Side(style="thin", color="D9D9D9")


def _f(**k):
    return Font(name=FONT, **k)


def _tytul(ws, tekst, pod=None):
    ws["A1"] = tekst
    ws["A1"].font = _f(size=14, bold=True, color=GRANAT)
    if pod:
        ws["A2"] = pod
        ws["A2"].font = _f(size=9, italic=True, color="595959")


def _tabela(ws, r0, c0, naglowki, wiersze, formaty=None, szerokosci=None):
    """Nagłówek + wiersze (wartości albo formuły '=...'). Zwraca (pierwszy, ostatni) wiersz danych."""
    formaty = formaty or {}
    for j, n in enumerate(naglowki):
        c = ws.cell(row=r0, column=c0 + j, value=n)
        c.font, c.fill = _f(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=GRANAT)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, w in enumerate(wiersze, start=1):
        for j, v in enumerate(w):
            c = ws.cell(row=r0 + i, column=c0 + j, value=None if (isinstance(v, float) and pd.isna(v)) else v)
            c.font, c.border = _f(), Border(bottom=CIENKA)
            if j in formaty:
                c.number_format = formaty[j]
    for j, s in enumerate(szerokosci or []):
        ws.column_dimensions[get_column_letter(c0 + j)].width = s
    return r0 + 1, r0 + len(wiersze)


def _wykres(typ, tytul, os_y, ws, kol_x, kolumny, r1, r2, kolory, kotwica, szer=18, wys=8, os_x=None, serie_z_naglowka=True):
    ch = typ()
    ch.title, ch.y_axis.title, ch.height, ch.width = tytul, os_y, wys, szer
    if os_x:
        ch.x_axis.title = os_x
    for k, kolor in zip(kolumny, kolory):
        ch.add_data(Reference(ws, min_col=k, min_row=r1 - 1 if serie_z_naglowka else r1, max_row=r2), titles_from_data=serie_z_naglowka)
        s = ch.series[-1]
        if typ is LineChart:
            s.graphicalProperties.line.solidFill, s.graphicalProperties.line.width, s.smooth = kolor, 20000, False
        else:
            s.graphicalProperties.solidFill = s.graphicalProperties.line.solidFill = kolor
    ch.set_categories(Reference(ws, min_col=kol_x, min_row=r1, max_row=r2))
    ch.legend.position = "b"
    ws.add_chart(ch, kotwica)
    return ch


def raport_excel(oid, zrodlo="", s=None, dz=None, jutro=None, mies=None, wynik=None, met=None, tydzien=None, bledy=None,
                 bledy_test=None, plan=None, wejscie=None, raport_llm=None, fakty=None):
    """Zwraca bajty pliku .xlsx. s, dz - z podsumowanie_klienta.podsumuj; plan = (dzienny, tygodnie, miesiace, start);
    wejscie - dane wejściowe godzinowo (zakładka Prognoza – szczegóły); bledy_test - {dni: błąd z testu}."""
    wb = Workbook()
    wp = wb.active
    wp.title = "Podsumowanie"
    _tytul(wp, f"Prognoza zużycia energii – pompownia {oid}",
           f"Źródło danych: {zrodlo or 'baza danych'} · wygenerowano {datetime.now():%d.%m.%Y %H:%M} · "
           f"liczby w tabeli liczone formułami z arkuszy obok")
    kluczowe = []                                                   # (etykieta, wartość/formuła, format, opis)

    # ------------------------------------------------------------------ Jutro godzinowo
    if jutro is not None and len(jutro):
        wj = wb.create_sheet("Jutro godzinowo")
        _tytul(wj, "Prognoza na kolejne 24 godziny", "Godzina lokalna, kWh zużyte w tej godzinie")
        r1, r2 = _tabela(wj, 3, 1, ["godzina", "prognoza [kWh]"],
                         [[f"{t:%d.%m %H:%M}", round(float(v), 2)] for t, v in zip(jutro["czas_lokalny"], jutro["prognoza"])],
                         {1: "0.0"}, [16, 16])
        _wykres(BarChart, "Prognoza zużycia godzina po godzinie", "kWh", wj, 1, [2], r1, r2, [NIEBIESKI], "D3")
        zakres = f"'Jutro godzinowo'!B{r1}:B{r2}"
        kluczowe += [("Prognoza na 24 h [kWh]", f"=SUM({zakres})", "#,##0", f"od {jutro['czas_lokalny'].min():%d.%m.%Y %H:%M}"),
                     ("Najwięcej energii – godzina", f"=INDEX('Jutro godzinowo'!A{r1}:A{r2},MATCH(MAX({zakres}),{zakres},0))", None, ""),
                     ("Najwięcej energii w godzinie [kWh]", f"=MAX({zakres})", "0.0", ""),
                     ("Najmniej energii w godzinie [kWh]", f"=MIN({zakres})", "0.0", "")]
        wp.add_chart(_kopiuj_wykres(wj, r1, r2), "E4")

    # ------------------------------------------------------------------ Dzień po dniu (sprawdzenie na danych z pliku)
    if dz is not None and len(dz):
        wd = wb.create_sheet("Dzień po dniu")
        _tytul(wd, "Jak trafiały prognozy – dzień po dniu",
               "Każdy dzień prognozowany dzień wcześniej, tylko z danych znanych w chwili prognozy")
        wiersze = []
        for i, r in enumerate(dz.itertuples(index=False), start=4):
            wiersze.append([pd.Timestamp(r.data).to_pydatetime(), round(float(r.rzeczywiste_kwh), 2), round(float(r.prognoza_kwh), 2),
                            f"=C{i}-B{i}", f'=IF(B{i}=0,"",D{i}/B{i})'])
        r1, r2 = _tabela(wd, 3, 1, ["dzień", "zużycie rzeczywiste [kWh]", "prognoza [kWh]", "różnica [kWh]", "różnica [%]"],
                         wiersze, {0: "dd.mm.yyyy", 1: "#,##0.0", 2: "#,##0.0", 3: "#,##0.0;-#,##0.0;-", 4: "0.0%;-0.0%;-"},
                         [12, 16, 14, 13, 11])
        _wykres(LineChart, "Zużycie rzeczywiste vs prognoza (z dnia wcześniej)", "kWh / doba", wd, 1, [2, 3], r1, r2,
                ["1A1A1A", CZERWONY], "G3", szer=22)
        _wykres(BarChart, "Błąd dzienny [%]", "%", wd, 1, [5], r1, r2, [SZARY], "G20", szer=22, wys=7)
        B, D, E = (f"'Dzień po dniu'!{k}{r1}:{k}{r2}" for k in "BDE")
        kluczowe += [("Średni błąd dobowy (WAPE)", f"=SUMPRODUCT(ABS({D}))/SUM({B})", "0.0%", "o ile średnio myliliśmy się w ciągu doby"),
                     ("Średni błąd [kWh na dobę]", f"=SUMPRODUCT(ABS({D}))/COUNT({B})", "#,##0", ""),
                     ("Dni z błędem poniżej 10%", f'=SUMPRODUCT(--(ABS({D})<0.1*{B}))&" z "&COUNT({B})', None, ""),
                     ("Średnie zużycie [kWh na dobę]", f"=AVERAGE({B})", "#,##0", "")]
        p = (met or {}).get("porownanie_WAPE_doba", {})
        if "naiwny_doba" in p:
            kluczowe.append(("Błąd metody „jutro jak dziś”", p["naiwny_doba"] / 100, "0.0%",
                             "wartość z backtestu modelu (te same doby)"))

    # ------------------------------------------------------------------ Miesięcznie
    if mies is not None and len(mies) > 0:
        wm = wb.create_sheet("Miesięcznie")
        _tytul(wm, "Sumy miesięczne – rzeczywiste vs prognoza")
        wiersze = [[str(m), round(float(r["kwh"]), 1), round(float(r["prognoza"]), 1), f'=IF(B{i}=0,"",(C{i}-B{i})/B{i})']
                   for i, (m, r) in enumerate(mies.iterrows(), start=4)]
        r1, r2 = _tabela(wm, 3, 1, ["miesiąc", "rzeczywiste [kWh]", "prognoza [kWh]", "różnica [%]"], wiersze,
                         {1: "#,##0", 2: "#,##0", 3: "0.0%;-0.0%;-"}, [12, 16, 14, 11])
        _wykres(BarChart, "Sumy miesięczne", "kWh", wm, 1, [2, 3], r1, r2, ["1A1A1A", CZERWONY], "F3")

    # ------------------------------------------------------------------ Tydzień
    if tydzien is not None and len(tydzien):
        wt = wb.create_sheet("Tydzień")
        _tytul(wt, "Prognoza na kolejne dni", "Każdy dzień liczony osobnym modelem, z prognozą pogody wydaną z takim wyprzedzeniem")
        r1h = 4
        godz = [[f"{t:%d.%m %H:%M}", int(k), round(float(v), 2)]
                for t, k, v in zip(tydzien["czas_lokalny"], tydzien["dzien_naprzod"], tydzien["prognoza"])]
        h1, h2 = _tabela(wt, 3, 10, ["godzina", "dzień naprzód", "prognoza [kWh]"], godz, {2: "0.0"}, [14, 12, 14])
        dni = sorted(tydzien["dzien_naprzod"].unique())
        wiersze = []
        for i, k in enumerate(dni, start=r1h):
            g = tydzien[tydzien["dzien_naprzod"] == k]
            wiersze.append([f"+{k}", f"{g['czas_lokalny'].min():%d.%m %H:%M}", f"{g['czas_lokalny'].max():%d.%m %H:%M}",
                            f"=SUMIFS($L${h1}:$L${h2},$K${h1}:$K${h2},{k})", f"=_xlfn.MAXIFS($L${h1}:$L${h2},$K${h1}:$K${h2},{k})",
                            (bledy_test or {}).get(k, None), (bledy or {}).get(k, None)])
        r1, r2 = _tabela(wt, 3, 1, ["dzień", "od", "do", "prognoza [kWh]", "szczyt [kWh/h]", "typowy błąd z testu [%]",
                                    "błąd na pliku [%]"], wiersze, {3: "#,##0", 4: "0.0", 5: "0.0", 6: "0.0"}, [7, 12, 12, 14, 13, 14, 13])
        wt.cell(row=r2 + 1, column=1, value="Razem").font = _f(bold=True)
        wt.cell(row=r2 + 1, column=4, value=f"=SUM(D{r1}:D{r2})").number_format = "#,##0"
        wt.cell(row=r2 + 2, column=1, value="Błędy: „typowy z testu” – python main.py horyzont; „na pliku” – sprawdzenie na dniach "
                                            "z pliku (dni +2…+7 modelem zapisanym).").font = _f(size=8, italic=True, color="595959")
        _wykres(LineChart, "Prognoza godzina po godzinie na kolejne dni", "kWh / h", wt, 10, [12], h1, h2, [NIEBIESKI],
                f"A{r2 + 4}", szer=24, serie_z_naglowka=True)
        _wykres(BarChart, "Prognoza dobowa", "kWh", wt, 1, [4], r1, r2, [GRANAT], f"A{r2 + 21}", szer=14, wys=7)
        kluczowe.append((f"Prognoza na {len(dni)} dni [kWh]", f"=SUM('Tydzień'!D{r1}:D{r2})", "#,##0", ""))

    # ------------------------------------------------------------------ Plan 2 miesiące
    if plan is not None:
        pdz, tyg, pmies, start = plan
        wpl = wb.create_sheet("Plan 2 miesiące")
        _tytul(wpl, "Plan na 2 miesiące – zużycie dobowe",
               "P50 = najbardziej prawdopodobne; P10–P90 = przedział, w którym mieści się ok. 80% dni. Bez prognozy pogody "
               "(typowa pogoda dla pory roku) – do budżetu i zakupu energii")
        wiersze = [[pd.Timestamp(r.dzien).to_pydatetime(), int(r.dni), round(float(r.p50), 1), round(float(r.p10), 1),
                    round(float(r.p90), 1), f"=INT((B{i}-1)/7)+1", pd.Timestamp(r.dzien).strftime("%Y-%m")]
                   for i, r in enumerate(pdz.itertuples(index=False), start=4)]
        r1, r2 = _tabela(wpl, 3, 1, ["dzień", "dni naprzód", "P50 [kWh]", "P10 [kWh]", "P90 [kWh]", "tydzień", "miesiąc"],
                         wiersze, {0: "dd.mm.yyyy", 2: "#,##0", 3: "#,##0", 4: "#,##0"}, [12, 10, 11, 11, 11, 9, 10])
        A, B, C, Dk, Ek, F, G = (f"${k}${r1}:${k}${r2}" for k in "ABCDEFG")
        tw = [[int(t), f"=_xlfn.MINIFS({A},{F},I{j})", f"=_xlfn.MAXIFS({A},{F},I{j})", f"=SUMIFS({C},{F},I{j})",
               f"=SUMIFS({Dk},{F},I{j})", f"=SUMIFS({Ek},{F},I{j})"] for j, t in enumerate(tyg["tydzien"], start=4)]
        t1, t2 = _tabela(wpl, 3, 9, ["tydzień", "od", "do", "P50 [kWh]", "P10 [kWh]", "P90 [kWh]"], tw,
                         {1: "dd.mm", 2: "dd.mm", 3: "#,##0", 4: "#,##0", 5: "#,##0"}, [9, 9, 9, 11, 11, 11])
        m0 = t2 + 3
        mw = [[str(m), f"=COUNTIF({G},I{j})", f"=SUMIFS({C},{G},I{j})", f"=SUMIFS({Dk},{G},I{j})", f"=SUMIFS({Ek},{G},I{j})"]
              for j, m in enumerate(pmies["miesiac"], start=m0 + 1)]
        m1, m2 = _tabela(wpl, m0, 9, ["miesiąc", "dni", "P50 [kWh]", "P10 [kWh]", "P90 [kWh]"], mw, {2: "#,##0", 3: "#,##0", 4: "#,##0"})
        wpl.cell(row=m2 + 1, column=9, value="Zakresy tygodni i miesięcy = suma dziennych granic (zakres ostrożny).") \
            .font = _f(size=8, italic=True, color="595959")
        _wykres(LineChart, "Plan dobowy: P50 i przedział P10–P90", "kWh / doba", wpl, 1, [3, 4, 5], r1, r2,
                [CZERWONY, "9DC3E6", "9DC3E6"], f"I{m2 + 3}", szer=24)
        _wykres(BarChart, "Plan tygodniowy (P50)", "kWh / tydzień", wpl, 9, [12], t1, t2, [GRANAT], f"I{m2 + 20}", szer=16, wys=7)
        kluczowe += [("Plan: najbliższe 4 tygodnie [kWh]", f"=SUMIFS('Plan 2 miesiące'!{C},'Plan 2 miesiące'!{B},\"<=28\")",
                      "#,##0", "P50"),
                     ("Plan: 60 dni [kWh]", f"=SUM('Plan 2 miesiące'!{C})", "#,##0", f"od {pdz['dzien'].min():%d.%m.%Y}")]

    # ------------------------------------------------------------------ Pogoda (dane wejściowe dobowo)
    if wejscie is not None and len(wejscie):
        wpg = wb.create_sheet("Pogoda")
        _tytul(wpg, "Zużycie na tle pogody – dobowo", "Deszcz zmierzony vs prognoza deszczu wydana dzień wcześniej (z niej korzysta model)")
        g = wejscie.groupby(wejscie["czas_lokalny"].dt.date)
        dd = pd.DataFrame({"rz": g["rzeczywiste_kwh"].sum(min_count=20), "pr": g["prognoza_kwh"].sum(),
                           "op": g["opad_mm"].sum(min_count=1), "pop": g["prognoza_opadu_mm"].sum(min_count=1),
                           "t": g["temperatura_c"].mean()})
        wiersze = [[pd.Timestamp(i).to_pydatetime(), *[None if pd.isna(v) else round(float(v), 2) for v in r]]
                   for i, r in dd.iterrows()]
        r1, r2 = _tabela(wpg, 3, 1, ["dzień", "zużycie rzeczywiste [kWh]", "prognoza [kWh]", "deszcz [mm]",
                                     "prognoza deszczu [mm]", "temperatura [°C]"], wiersze,
                         {0: "dd.mm.yyyy", 1: "#,##0", 2: "#,##0", 3: "0.0", 4: "0.0", 5: "0.0"}, [12, 16, 13, 11, 14, 13])
        kwh = _wykres(LineChart, "Zużycie energii i deszcz", "kWh / doba", wpg, 1, [2, 3], r1, r2, ["1A1A1A", CZERWONY], "H3", szer=24)
        wpg._charts.remove(kwh)
        deszcz = BarChart()
        for k, kol in ((4, NIEBIESKI), (5, ZIELONY)):
            deszcz.add_data(Reference(wpg, min_col=k, min_row=r1 - 1, max_row=r2), titles_from_data=True)
            deszcz.series[-1].graphicalProperties.solidFill = kol
        deszcz.y_axis.axId, deszcz.y_axis.title = 200, "mm"
        deszcz.y_axis.crosses = "max"
        kwh += deszcz
        wpg.add_chart(kwh, "H3")
        _wykres(LineChart, "Temperatura", "°C", wpg, 1, [6], r1, r2, ["ED7D31"], "H20", szer=24, wys=6)

    # ------------------------------------------------------------------ Raport AI
    if raport_llm:
        wr = wb.create_sheet("Raport AI")
        _tytul(wr, "Raport opisowy (lokalny model językowy)", "Tekst sformułowany przez LLM z faktów policzonych w Pythonie")
        wr.column_dimensions["A"].width = 120
        for i, akapit in enumerate([a for a in raport_llm.split("\n") if a.strip()], start=4):
            c = wr.cell(row=i, column=1, value=akapit)
            c.font, c.alignment = _f(), Alignment(wrap_text=True, vertical="top")
        if fakty:
            r = wr.max_row + 2
            wr.cell(row=r, column=1, value="Fakty źródłowe").font = _f(bold=True)
            for j, linia in enumerate(fakty.split("\n"), start=r + 1):
                wr.cell(row=j, column=1, value=linia).font = _f(size=9, color="595959")

    # ------------------------------------------------------------------ Godzinowo (pełne)
    if wynik is not None and len(wynik):
        wg = wb.create_sheet("Godzinowo")
        _tytul(wg, "Dane godzinowe: rzeczywiste i prognoza")
        _tabela(wg, 3, 1, ["godzina", "rzeczywiste [kWh]", "prognoza [kWh]"],
                [[f"{t:%Y-%m-%d %H:%M}", None if pd.isna(a) else round(float(a), 3), None if pd.isna(b) else round(float(b), 3)]
                 for t, a, b in zip(wynik["czas_lokalny"], wynik["rzeczywiste"], wynik["prognoza"])],
                {1: "0.000", 2: "0.000"}, [18, 16, 14])

    # ------------------------------------------------------------------ Podsumowanie: tabela + opis
    r1, r2 = _tabela(wp, 4, 1, ["co", "wartość", "uwagi"], [[a, b, d] for a, b, _, d in kluczowe], None, [38, 16, 40])
    for i, (_, _, fmt, _) in enumerate(kluczowe):
        if fmt:
            wp.cell(row=r1 + i, column=2).number_format = fmt
    if s is not None:
        r = r2 + 2
        wp.cell(row=r, column=1, value="Opis").font = _f(bold=True, color=GRANAT)
        wp.merge_cells(start_row=r + 1, start_column=1, end_row=r + 12, end_column=3)
        c = wp.cell(row=r + 1, column=1, value=s["tekst"].replace("**", ""))
        c.font, c.alignment = _f(size=10), Alignment(wrap_text=True, vertical="top")
    wb.calculation.fullCalcOnLoad = True                         # Excel przelicza formuły przy otwarciu
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _kopiuj_wykres(wj, r1, r2):
    """Wykres jutra także na arkuszu Podsumowanie (seria z arkusza Jutro godzinowo)."""
    ch = BarChart()
    ch.title, ch.y_axis.title, ch.height, ch.width = "Prognoza na 24 h [kWh]", "kWh", 7.5, 16
    ch.add_data(Reference(wj, min_col=2, min_row=r1 - 1, max_row=r2), titles_from_data=True)
    ch.series[0].graphicalProperties.solidFill = ch.series[0].graphicalProperties.line.solidFill = NIEBIESKI
    ch.set_categories(Reference(wj, min_col=1, min_row=r1, max_row=r2))
    ch.legend = None
    return ch
