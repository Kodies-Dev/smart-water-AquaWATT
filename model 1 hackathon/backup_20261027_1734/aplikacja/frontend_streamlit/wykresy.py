"""
Wszystkie wykresy aplikacji, zrobione w Plotly (interaktywne - przyblizanie,
przesuwanie, dymki po najechaniu).

Kazda metoda buduje jeden wykres i zwraca gotowy obiekt figury - nie
wywoluje sama st.plotly_chart, to robi Wykresy.show() w zakladce, zeby
mozna bylo w jednym miejscu ustawic pasek narzedzi.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frontend_streamlit.styles import COL_PRIMARY, COL_ACCENT, COL_ANOM, PLOT_LAYOUT, AXIS_STYLE
from frontend_streamlit.narzedzia import Narzedzia


class Wykresy:
    """Cala fabryka wykresow - kazda metoda to jeden typ wykresu. Statyczne,
    bo nie trzymamy tu zadnego stanu, tylko budujemy figury na zadanie.
    leci to tak rodzaj wykresy -> style -> show
    """

    @staticmethod
    def style_fig(fig, title, x_title=None, y_title=None, limits=None, height=420):
        """Nadaje wspolny wyglad i naklada recznie wpisane zakresy osi."""
        fig.update_layout(title=title, height=height, **PLOT_LAYOUT)  # tytul wysokosc i ustawienia globalne z gory
        fig.update_xaxes(title_text=x_title, **AXIS_STYLE)
        fig.update_yaxes(title_text=y_title, **AXIS_STYLE)
        if limits:
            x_min, x_max, y_min, y_max = limits
            if x_min is not None or x_max is not None:
                fig.update_xaxes(range=[x_min, x_max])
            if y_min is not None or y_max is not None:
                fig.update_yaxes(range=[y_min, y_max])
        return fig

    @staticmethod
    def show(fig, key=None):
        """Jedno miejsce na ustawienia paska narzedzi Plotly. key - gdy ten sam wykres jest na stronie dwa razy."""
        st.plotly_chart(fig, width="stretch", key=key,
                        config={"displaylogo": False,
                                "modeBarButtonsToRemove": ["lasso2d", "select2d"]})

    @staticmethod
    def anom_hover(anom, col, extra_cols): #anom to df, col to kolumna extra to sa extra kolumny do opisania
        """Buduje tekst dymka dla anomalii - wartosc plus kontekst z innych kolumn."""
        linie = []  # gotowe teksty dymkow
        for i in anom.index:
            czesci = [f"<b>wiersz {i}</b>", f"{col}: {anom.loc[i, col]}"]  # wiersz i wartosc z kolumny
            for c in extra_cols:  # petla przez dodatkowe kolumny
                if c in anom.columns:
                    v = anom.loc[i, c]
                    if isinstance(v, float):
                        v = round(v, 3)  # czytelnosc
                    czesci.append(f"{c}: {v}")
            linie.append("<br>".join(czesci))
        return linie

    @staticmethod
    def fig_line(df, cols, title, limits=None):
        """interaktywny wykres liniowy dla wybranych kolumn"""
        fig = go.Figure()  # z plotly wykres liniowy
        for c in cols:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[c], name=c, mode="lines",
                line=dict(width=1.6),
                hovertemplate=f"<b>{c}</b><br>wiersz %{{x}}<br>wartosc %{{y}}<extra></extra>",
            ))  # dodaje do wykresu nowa serie danych punktowo liniowych
        return Wykresy.style_fig(fig, title, "indeks wiersza", None, limits)

    @staticmethod
    def fig_hist(df, col, bins, limits=None):
        """histogram"""
        fig = go.Figure(go.Histogram(
            x=df[col].dropna(), nbinsx=int(bins), marker_color=COL_PRIMARY,
            marker_line=dict(color="white", width=1),
            hovertemplate="przedzial %{x}<br>liczba wierszy %{y}<extra></extra>",  # dymek po najechaniu tooltip
        ))
        return Wykresy.style_fig(fig, f"Histogram: {col}", col, "liczba wierszy", limits)

    @staticmethod
    def fig_box(df, cols, limits=None):
        """boxplot"""
        fig = go.Figure()
        for c in cols:
            fig.add_trace(go.Box(y=df[c].dropna(), name=c, marker_color=COL_PRIMARY,
                                 boxpoints="outliers"))
        return Wykresy.style_fig(fig, "Boxplot (rozklad i outliery IQR)", None, None, limits)

    @staticmethod
    def fig_corr(df, cols):
        """korelacja"""
        corr = df[cols].corr()
        fig = go.Figure(go.Heatmap(
            z=corr.values, x=cols, y=cols, zmin=-1, zmax=1, colorscale="RdYlGn",
            text=corr.round(2).values, texttemplate="%{text}",
            hovertemplate="%{y} vs %{x}<br>korelacja %{z:.3f}<extra></extra>",
        ))
        fig = Wykresy.style_fig(fig, "Korelacje miedzy kolumnami", None, None, None, height=520)
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=False)
        return fig

    @staticmethod
    def fig_rolling_anom(df, col, limits=None):
        """limits to bylo xmin ymin itp"""
        plot_df, step = Narzedzia.downsample(df)  # aktualnie zero manualnie
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=plot_df.index, y=plot_df[col], name=col, mode="lines",
            line=dict(color=COL_PRIMARY, width=1.6),
            hovertemplate=f"wiersz %{{x}}<br>{col} %{{y}}<extra></extra>",
        ))  # linia wartosci
        if f"{col}_rolling_mean" in df.columns:
            fig.add_trace(go.Scatter(
                x=plot_df.index, y=plot_df[f"{col}_rolling_mean"], name="srednia kroczaca",
                mode="lines", line=dict(color=COL_ACCENT, width=1.6, dash="dash"),
                hovertemplate="wiersz %{x}<br>srednia %{y:.2f}<extra></extra>",
            ))
        anom = df[df["Anomaly_Final"] == 1]  # RYSUJE czerwone kwadraty tam gdzie jest anomalia
        if len(anom) > 0:
            fig.add_trace(go.Scatter(
                x=anom.index, y=anom[col], name="anomalia", mode="markers",
                marker=dict(color=COL_ANOM, size=9, symbol="square"),
                text=Wykresy.anom_hover(anom, col, ["Anomaly_Votes", "Has_Outlier",
                                            f"{col}_zscore", "Rodzaj_Anomalii"]),
                hovertemplate="%{text}<extra></extra>",
            ))  # te czerwone kwadraty pokazujace wykryte anomalie
        tytul = f"{col} - wartosc vs srednia kroczaca" + (f" (co {step}. punkt)" if step > 1 else "")
        return Wykresy.style_fig(fig, tytul, "indeks wiersza", col, limits)

    @staticmethod
    def fig_zscore_anom(df, col, threshold=3.0, limits=None):
        plot_df, _ = Narzedzia.downsample(df)  # co ktoras wartosc dla klarownosci
        zc = f"{col}_zscore"  # konwencja nazewnicza - kazda kolumna ma to po analizie
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=plot_df.index, y=plot_df[zc], name="z-score", mode="markers",  # indeks i wartosc tego guana
            marker=dict(color=COL_PRIMARY, size=5, symbol="square"),
            hovertemplate=f"wiersz %{{x}}<br>z-score %{{y:.2f}}<extra></extra>",
        ))  # to po prostu pokazuje te niebieskie kwadraty z score dla wszystkiego
        anom = df[df["Anomaly_Final"] == 1]  # prawdziwa anomalia
        if len(anom) > 0:  # niech bedzie wiecej niz 0 anomalii
            fig.add_trace(go.Scatter(
                x=anom.index, y=anom[zc], name="anomalia", mode="markers",
                marker=dict(color=COL_ANOM, size=10, symbol="square"),
                text=Wykresy.anom_hover(anom, col, [zc, "Anomaly_Votes", "Has_Outlier", "Rodzaj_Anomalii"]),
                hovertemplate="%{text}<extra></extra>",
            ))
        for y in (threshold, -threshold):
            fig.add_hline(y=y, line=dict(color="#8C8C8C", width=1, dash="dash"))
        fig.add_annotation(x=1, xref="paper", y=threshold, text=f"prog +/-{threshold}",
                           showarrow=False, font=dict(size=10, color="#8C8C8C"),
                           xanchor="right", yanchor="bottom")
        return Wykresy.style_fig(fig, f"{col} - z-score", "indeks wiersza", "z-score", limits)

    @staticmethod
    def fig_grupy(df, col, group_col, time_col, jednostki, limits=None):
        """Szeregi czasowe kilku jednostek na jednym wykresie, z zaznaczonymi anomaliami.
        group_col to kolumna z jednostki"""
        fig = go.Figure()
        for j in jednostki:
            sub = df[df[group_col].astype(str) == str(j)].sort_values(time_col)
            fig.add_trace(go.Scatter(
                x=sub[time_col], y=sub[col], name=str(j), mode="lines+markers",
                line=dict(width=1.6), marker=dict(size=5, symbol="square"),
                hovertemplate=f"<b>{j}</b><br>%{{x}}<br>{col} %{{y}}<extra></extra>",
            ))
        anom = df[(df["Anomaly_Final"] == 1) &
                  (df[group_col].astype(str).isin([str(x) for x in jednostki]))]
        if len(anom) > 0:
            fig.add_trace(go.Scatter(
                x=anom[time_col], y=anom[col], name="anomalia", mode="markers",
                marker=dict(color=COL_ANOM, size=14, symbol="square-open", line=dict(width=2.5)),
                text=Wykresy.anom_hover(anom, col, [group_col, "Anomaly_Votes",
                                            "Nagla_Zmiana", "Odstaje_Od_Innych", "Rodzaj_Anomalii"]),
                hovertemplate="%{text}<extra></extra>",
            ))
        return Wykresy.style_fig(fig, f"{col} wedlug jednostek", str(time_col), col, limits, height=480)

    @staticmethod
    def fig_votes(df, limits=None):
        """barchart slupki dla wynikow modeli, do podgladu"""
        counts = {
            "Isolation Forest": int(df["Anomaly_IF"].sum()),
            "LOF": int(df["Anomaly_LOF"].sum()),
            "One-Class SVM": int(df["Anomaly_SVM"].sum()),
            "Final (>=2/3)": int(df["Anomaly_Final"].sum()),
        }
        fig = go.Figure(go.Bar(
            x=list(counts.keys()), y=list(counts.values()),
            marker_color=[COL_PRIMARY] * 3 + [COL_ANOM],
            marker_line=dict(color="#8C8C8C", width=1),
            text=list(counts.values()), textposition="outside",
            hovertemplate="%{x}<br>wykryl %{y} wierszy<extra></extra>",
        ))
        return Wykresy.style_fig(fig, "Liczba wykrytych anomalii per model", None, "liczba wierszy", limits)

    @staticmethod
    def fig_anom_per_col(df, num_cols, limits=None):
        """Ile anomalii ma glowna przyczyne w danej kolumnie (najwyzszy |z-score|)."""
        anom = df[df["Anomaly_Final"] == 1]
        if len(anom) == 0:
            return None
        zcols = [f"{c}_zscore" for c in num_cols if f"{c}_zscore" in df.columns]
        main = anom[zcols].abs().idxmax(axis=1).str.replace("_zscore", "", regex=False)
        counts = main.value_counts()
        fig = go.Figure(go.Bar(
            x=list(counts.index), y=list(counts.values), marker_color=COL_ACCENT,
            marker_line=dict(color="#8C8C8C", width=1),
            text=list(counts.values), textposition="outside",
            hovertemplate="kolumna %{x}<br>%{y} anomalii<extra></extra>",
        ))
        return Wykresy.style_fig(fig, "Glowna przyczyna anomalii wg kolumny", None, "liczba anomalii", limits)


    # ---------------------------------------------------------------- wykresy pod siec kanalizacyjna (hackathon)

    KOLORY_TYPOW = {"dopływ opadowy": "#378ADD", "roztopy": "#85B7EB", "infiltracja / dopływ bez deszczu": "#D85A30",
                    "nadmiar bez deszczu": "#EF9F27", "spadek – awaria / przerwa": COL_ANOM,
                    "spadek sprawności pomp": "#7F77DD", "zmiana nastaw sterowania": "#5DCAA5",
          "spiętrzenie w zbiorniku": "#993556",
                    "inne / nietypowy dzień": "#8C8C8C"}

    @staticmethod
    def fig_os_czasu(df, obiekt, limits=None):
        """Doba po dobie dla jednej pompowni: rzeczywiste vs baza bezdeszczowa, opad (os prawa), anomalie wg typu."""
        from plotly.subplots import make_subplots
        g = df[df["obiekt_id"] == obiekt].sort_values("dzien")
        przeplyw = g["m3"].notna().mean() > 0.5
        y, baza, jedn = ("m3", "m3_baza", "m³") if przeplyw else ("kwh", "kwh_baza", "kWh")
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=g["dzien"], y=g["opad_doba"], name="opad [mm]", marker_color="#BDD7EE", opacity=0.6,
                             hovertemplate="%{x|%Y-%m-%d}<br>opad %{y:.1f} mm<extra></extra>"), secondary_y=True)
        fig.add_trace(go.Scatter(x=g["dzien"], y=g[y], name=f"rzeczywiste [{jedn}/doba]", mode="lines",
                                 line=dict(color=COL_PRIMARY, width=1.4),
                                 hovertemplate=f"%{{x|%Y-%m-%d}}<br>{jedn} %{{y:.0f}}<extra></extra>"))
        fig.add_trace(go.Scatter(x=g["dzien"], y=g[baza], name="baza bezdeszczowa", mode="lines",
                                 line=dict(color=COL_ACCENT, width=1.2, dash="dash"),
                                 hovertemplate=f"%{{x|%Y-%m-%d}}<br>baza %{{y:.0f}}<extra></extra>"))
        a = g[g["Anomaly_Final"] == 1]
        for typ, kolor in Wykresy.KOLORY_TYPOW.items():
            t = a[a["typ"] == typ]
            if len(t):
                fig.add_trace(go.Scatter(x=t["dzien"], y=t[y], name=f"{typ} ({len(t)})", mode="markers",
                                         marker=dict(color=kolor, size=10, symbol="square", line=dict(color="white", width=1)),
                                         text=t["opis"], hovertemplate="%{text}<extra></extra>"))
        fig.update_yaxes(title_text="opad [mm/doba]", secondary_y=True, showgrid=False,
                         range=[0, max(1, g["opad_doba"].max()) * 3])
        return Wykresy.style_fig(fig, f"{obiekt} - doba po dobie", None, f"{jedn} / doba", limits, height=460)

    @staticmethod
    def fig_ranking(rank, limits=None):
        """Ile wody / energii ponad baze bezdeszczowa ma kazda pompownia."""
        fig = go.Figure()
        for kol, nazwa, kolor in [("udzial_wod_obcych_proc", "wody obce w przeplywie [%]", COL_PRIMARY),
                                  ("nadwyzka_energii_proc", "energia ponad baze bezdeszczowa [%]", COL_ACCENT)]:
            if kol in rank:
                fig.add_trace(go.Bar(x=rank["obiekt"], y=rank[kol], name=nazwa, marker_color=kolor,
                                     text=rank[kol].round(1), textposition="outside",
                                     hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>"))
        fig.update_layout(barmode="group")
        return Wykresy.style_fig(fig, "Ranking pompowni - wody obce", None, "%", limits)

    @staticmethod
    def fig_przyczyny(licz, limits=None):
        """Co najczesciej bylo glowna przyczyna anomalii (cechy skutku: woda, energia, pompy)."""
        l = licz.sort_values("udzial_proc")
        fig = go.Figure(go.Bar(x=l["udzial_proc"], y=l["nazwa"], orientation="h", marker_color=COL_ACCENT,
                               marker_line=dict(color="#8C8C8C", width=1), text=l["anomalii"], textposition="outside",
                               hovertemplate="%{y}<br>%{x:.1f}% anomalii<extra></extra>"))
        return Wykresy.style_fig(fig, "Glowna przyczyna anomalii", "% anomalii", None, limits, height=380)

    @staticmethod
    def fig_typy(df, limits=None):
        """Liczba anomalii wg typu, w podziale na pompownie."""
        a = df[df["Anomaly_Final"] == 1]
        t = a.groupby(["obiekt_id", "typ"]).size().unstack(fill_value=0)
        fig = go.Figure()
        for typ in t.columns:
            fig.add_trace(go.Bar(x=t.index, y=t[typ], name=typ, marker_color=Wykresy.KOLORY_TYPOW.get(typ, "#8C8C8C"),
                                 hovertemplate=f"%{{x}}<br>{typ}: %{{y}}<extra></extra>"))
        fig.update_layout(barmode="stack")
        return Wykresy.style_fig(fig, "Anomalie wg typu", None, "liczba dob", limits)


    # ---------------------------------------------------------------- prognoza energii (zakladka Prognoza)

    @staticmethod
    def fig_prognoza_24h(wynik, jutro, limits=None):
        """Ostatni tydzien godzinowo (rzeczywiste vs prognoza) + kolejne 24 h."""
        o = wynik[wynik["czas"] >= jutro["czas"].min() - pd.Timedelta(days=7)]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=o["czas_lokalny"], y=o["rzeczywiste"], name="rzeczywiste", mode="lines",
                                 line=dict(color=COL_PRIMARY, width=1.6)))
        fig.add_trace(go.Scatter(x=o["czas_lokalny"], y=o["prognoza"], name="prognoza doba wczesniej", mode="lines",
                                 line=dict(color=COL_ACCENT, width=1.4, dash="dot")))
        fig.add_trace(go.Scatter(x=jutro["czas_lokalny"], y=jutro["prognoza"], name="prognoza na 24 h", mode="lines+markers",
                                 line=dict(color=COL_ANOM, width=2), marker=dict(size=5, symbol="square")))
        fig.add_vrect(x0=jutro["czas_lokalny"].min(), x1=jutro["czas_lokalny"].max(), fillcolor=COL_ANOM, opacity=0.06,
                      line_width=0)
        return Wykresy.style_fig(fig, "Ostatni tydzien i prognoza na kolejne 24 h", None, "kWh / h", limits, height=440)

    @staticmethod
    def fig_prognoza_dobowa(wynik, limits=None):
        """Backtest: zuzycie dobowe rzeczywiste vs prognoza wydana dzien wczesniej."""
        w = wynik.dropna(subset=["rzeczywiste"])
        g = w.assign(dzien=w["czas_lokalny"].dt.date).groupby("dzien")
        dz = g[["rzeczywiste", "prognoza"]].sum()[g["rzeczywiste"].count() >= 23]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dz.index, y=dz["rzeczywiste"], name="rzeczywiste", mode="lines",
                                 line=dict(color=COL_PRIMARY, width=1.6)))
        fig.add_trace(go.Scatter(x=dz.index, y=dz["prognoza"], name="prognoza doba wczesniej", mode="lines",
                                 line=dict(color=COL_ACCENT, width=1.4)))
        return Wykresy.style_fig(fig, "Backtest - zuzycie dobowe", None, "kWh / doba", limits, height=400)


    # ---------------------------------------------------------------- wyniki modeli prognozy (zakladka Wyniki modeli)

    @staticmethod
    def fig_wape_warianty(met, nazwa, glowny, limits=None):
        r = met[met["obiekt"] == "RAZEM"].sort_values("WAPE_doba", ascending=False)
        r = r[~r["wariant"].str.startswith("xgb_transfer")]                 # transfer liczony tylko dla Rybnika
        kol = [COL_ANOM if w == glowny else ("#8C8C8C" if w in ("naiwny_doba", "naiwny_tydzien", "profil_4tyg") else
               (COL_ACCENT if w == "xgb_pogoda_rzeczywista" else COL_PRIMARY)) for w in r["wariant"]]
        fig = go.Figure(go.Bar(x=r["WAPE_doba"], y=[nazwa(w) for w in r["wariant"]], orientation="h", marker_color=kol,
                               text=r["WAPE_doba"].round(1), textposition="outside",
                               hovertemplate="%{y}<br>WAPE dobowe %{x:.1f}%<extra></extra>"))
        return Wykresy.style_fig(fig, "Wszystkie warianty - WAPE dobowe na tescie (czerwony = model glowny, szary = proste reguly)",
                                 "WAPE dobowe [%]", None, limits, height=560)

    @staticmethod
    def fig_obiekty(met, warianty, nazwa, limits=None):
        t = met[met["obiekt"] != "RAZEM"]
        # te same kolory co na wykresie wszystkich wariantow: model glowny czerwony, reguly szare, idealna pogoda zielona
        kolory = {"xgb_prognoza_pogody": COL_ANOM, "naiwny_doba": "#D9D9D9", "naiwny_tydzien": "#A6A6A6",
                  "profil_4tyg": "#737373", "xgb_pogoda_rzeczywista": COL_ACCENT}
        fig = go.Figure()
        for w in warianty:
            g = t[t["wariant"] == w]
            if len(g):
                fig.add_trace(go.Bar(x=g["obiekt"], y=g["WAPE_doba"], name=nazwa(w), marker_color=kolory.get(w, COL_PRIMARY),
                                     marker_line=dict(color="#8C8C8C", width=0.5), text=g["WAPE_doba"].round(1),
                                     textposition="outside", textfont=dict(size=10),
                                     hovertemplate=f"{nazwa(w)}<br>%{{x}}: %{{y:.1f}}%<extra></extra>"))
        fig.update_layout(barmode="group")
        return Wykresy.style_fig(fig, "Model vs proste reguly - per pompownia", None, "WAPE dobowe [%]", limits)

    @staticmethod
    def fig_sucho_mokro(met, warianty, nazwa, limits=None):
        r = met[(met["obiekt"] == "RAZEM") & met["wariant"].isin(warianty)].set_index("wariant").reindex(warianty).dropna(how="all")
        fig = go.Figure()
        for kol, opis, c in [("WAPE_doba_sucho", "doby suche", COL_ACCENT), ("WAPE_doba_mokro", "doby mokre (opad > 1 mm)", COL_PRIMARY)]:
            fig.add_trace(go.Bar(x=[nazwa(w) for w in r.index], y=r[kol], name=opis, marker_color=c,
                                 text=r[kol].round(1), textposition="outside"))
        fig.update_layout(barmode="group")
        return Wykresy.style_fig(fig, "Gdzie model sie myli - doby suche vs mokre", None, "WAPE dobowe [%]", limits)

    @staticmethod
    def fig_waznosc(waz, limits=None):
        def grupa(c):
            if c.startswith("prog_"): return "prognoza pogody"
            if c.startswith("opad"): return "opad (przeszly)"
            if c.startswith(("kwh_", "profil", "poziom")): return "historia zuzycia"
            if c.startswith("ob_"): return "pompownia"
            if c.endswith("_pr"): return "pogoda (przeszla)"
            return "kalendarz"
        g = waz.groupby(waz.index.map(grupa)).sum().sort_values()
        fig = go.Figure(go.Bar(x=100 * g / g.sum(), y=g.index, orientation="h", marker_color=COL_PRIMARY,
                               text=(100 * g / g.sum()).round(0).astype(int).astype(str) + "%", textposition="outside",
                               hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
        return Wykresy.style_fig(fig, "Z czego korzysta model glowny (waznosc cech wg grupy)", "% waznosci", None, limits, height=360)

    @staticmethod
    def fig_test_obiekt(prog, oid, warianty, nazwa, limits=None):
        g = prog[prog["obiekt_id"] == oid].copy()
        g["dzien"] = pd.to_datetime(g["czas"], utc=True).dt.tz_convert("Europe/Warsaw").dt.date
        grp = g.groupby("dzien")
        dz = grp[["kwh", *[w for w in warianty if w in g]]].sum()[grp["kwh"].count() >= 23]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dz.index, y=dz["kwh"], name="rzeczywiste", mode="lines", line=dict(color="#1A1A1A", width=1.8)))
        for w, c in zip([w for w in warianty if w in dz], [COL_ANOM, "#8C8C8C", COL_ACCENT]):
            fig.add_trace(go.Scatter(x=dz.index, y=dz[w], name=nazwa(w), mode="lines", line=dict(color=c, width=1.3)))
        return Wykresy.style_fig(fig, f"{oid} - zuzycie dobowe na tescie: rzeczywiste vs prognoza", None, "kWh / doba", limits)


    # ---------------------------------------------------------------- widok klienta (zakladka Twoja prognoza)

    @staticmethod
    def fig_jutro_slupki(jutro, limits=None):
        """Prognoza na kolejne 24 h - slupki godzinowe, szczyt na czerwono."""
        szczyt = jutro["prognoza"].idxmax()
        kol = [COL_ANOM if i == szczyt else COL_PRIMARY for i in jutro.index]
        fig = go.Figure(go.Bar(x=jutro["czas_lokalny"].dt.strftime("%H:%M"), y=jutro["prognoza"], marker_color=kol,
                               text=jutro["prognoza"].round(1), textposition="outside", textfont=dict(size=10),
                               hovertemplate="godz. %{x}<br>%{y:.1f} kWh<extra></extra>"))
        tytul = f"Prognoza zuzycia energii godzina po godzinie: {jutro['czas_lokalny'].min():%d.%m.%Y} (czerwony = najwiecej)"
        return Wykresy.style_fig(fig, tytul, "godzina", "kWh w godzinie", limits, height=400)

    @staticmethod
    def fig_trafnosc_dobowa(dz, limits=None):
        """Jak trafialy prognozy: zuzycie dobowe rzeczywiste vs prognoza (z dnia wczesniej) + blad dzienny."""
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.06)
        fig.add_trace(go.Scatter(x=dz["data"], y=dz["rzeczywiste_kwh"], name="zuzycie rzeczywiste", mode="lines",
                                 line=dict(color="#1A1A1A", width=1.8)), row=1, col=1)
        fig.add_trace(go.Scatter(x=dz["data"], y=dz["prognoza_kwh"], name="nasza prognoza (z dnia wczesniej)", mode="lines",
                                 line=dict(color=COL_ANOM, width=1.4)), row=1, col=1)
        kol = [COL_ACCENT if abs(v) < 10 else ("#EF9F27" if abs(v) < 20 else COL_ANOM) for v in dz["roznica_proc"]]
        fig.add_trace(go.Bar(x=dz["data"], y=dz["roznica_proc"], name="blad dzienny [%]", marker_color=kol,
                             hovertemplate="%{x}<br>blad %{y:+.1f}%<extra></extra>"), row=2, col=1)
        fig = Wykresy.style_fig(fig, "Jak trafialy prognozy - dzien po dniu (dol: blad dzienny, zielony < 10%)", None, None,
                                limits, height=520)
        fig.update_yaxes(title_text="kWh / doba", row=1, col=1)
        fig.update_yaxes(title_text="blad [%]", row=2, col=1)
        return fig
