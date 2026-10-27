"""
Zakladka Wyniki modeli - jak dobry jest model prognozy (wyniki python main.py model w folderze wyniki/):
porownanie wariantow, model vs proste reguly per pompownia, doby suche i mokre, waznosc cech, test vs rzeczywistosc.
"""

import pandas as pd
import streamlit as st

from backend_ml_llm.raport_prognozy import wczytaj_wyniki, nazwa, GLOWNY, REGULY
from frontend_streamlit.wykresy import Wykresy


def renderuj():
    st.subheader("Wyniki modeli prognozy")
    meta, met, prog, waz = wczytaj_wyniki()
    if met is None:
        st.info("Brak wynikow eksperymentow - uruchom `python main.py model` (ok. 2 min).")
        return

    r = met[met["obiekt"] == "RAZEM"].set_index("wariant")
    if GLOWNY in r.index:
        g = r.loc[GLOWNY]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("WAPE dobowe - model glowny", f"{g['WAPE_doba']:.1f}%")
        for c, w in zip([c2, c3, c4], ["profil_4tyg", "naiwny_doba", "naiwny_tydzien"]):
            if w in r.index:
                c.metric(nazwa(w), f"{r.loc[w, 'WAPE_doba']:.1f}%",
                         f"model lepszy o {100 * (1 - g['WAPE_doba'] / r.loc[w, 'WAPE_doba']):.0f}%", delta_color="off")
        st.caption("WAPE = suma |bledow| / suma zuzycia, liczone dla pelnych dob na zbiorze testowym (ostatnie 30% czasu "
                   "kazdej pompowni). Kazda doba prognozowana dzien wczesniej, tylko z danych znanych w chwili prognozy.")

    Wykresy.show(Wykresy.fig_wape_warianty(met, nazwa, GLOWNY))
    st.divider()
    Wykresy.show(Wykresy.fig_obiekty(met, [GLOWNY, *REGULY, "xgb_pogoda_rzeczywista"], nazwa))
    st.caption("Na spokojnych pompowniach (RU_ZMP, RY_PZ1) proste reguly sa mocne; najwiekszy zysk modelu jest tam, gdzie "
               "zuzycie mocno zalezy od deszczu (CH_T, RU_W).")

    if "WAPE_doba_sucho" in met:
        st.divider()
        Wykresy.show(Wykresy.fig_sucho_mokro(met, [GLOWNY, "profil_4tyg", "xgb_pogoda_rzeczywista"], nazwa))
        st.caption("Doba mokra = opad > 1 mm. Wiekszosc bledu to dni z ulewa - ogranicza nas trafnosc prognozy deszczu "
                   "sprzed doby (z idealna pogoda blad w dni mokre spada wyraznie).")

    if waz is not None:
        st.divider()
        Wykresy.show(Wykresy.fig_waznosc(waz))

    if prog is not None and GLOWNY in prog:
        st.divider()
        st.markdown("#### Prognoza vs rzeczywistosc na zbiorze testowym")
        obiekty = sorted(prog["obiekt_id"].unique())
        oid = st.selectbox("Pompownia", obiekty, index=obiekty.index("RY_PZ1") if "RY_PZ1" in obiekty else 0, key="wm_obiekt")
        Wykresy.show(Wykresy.fig_test_obiekt(prog, oid, [GLOWNY, "profil_4tyg"], nazwa))

    with st.expander("Pelna tabela WAPE dobowego [%]"):
        t = met.pivot(index="wariant", columns="obiekt", values="WAPE_doba")
        t = t[[c for c in t if c != "RAZEM"] + ["RAZEM"]]
        transfer = t.index.str.startswith("xgb_transfer")          # RAZEM liczone tylko z Rybnika - na koniec tabeli
        t = pd.concat([t[~transfer].sort_values("RAZEM"), t[transfer].sort_values("RAZEM")])
        t.index = [nazwa(i) for i in t.index]
        # Streamlit pokazuje puste komorki jako "None" niezaleznie od formatowania - podajemy gotowy tekst
        st.dataframe(t.apply(lambda k: k.map(lambda v: "–" if pd.isna(v) else f"{v:.1f}")), width="stretch",
                     height=(len(t) + 1) * 35 + 3)
        st.caption("Warianty 'bez Rybnika w treningu' sa na koncu: ich RAZEM liczone jest tylko z pompowni Rybnika.")
    if meta:
        st.caption(f"Zapisany model do pracy: {nazwa(meta['wariant'])}, {meta['drzew']} drzew, wytrenowany "
                   f"{meta['wytrenowano'][:16].replace('T', ' ')} na wszystkich danych ({meta['godzin']:,} h).")
