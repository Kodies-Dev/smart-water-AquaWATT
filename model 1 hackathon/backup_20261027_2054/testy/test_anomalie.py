"""Anomalie: zespół IF + LOF + One-Class SVM łapie wstrzyknięte zdarzenia i dobrze je nazywa."""
import numpy as np
import pandas as pd

from anomalie.detekcja import SKUTKI


def _zmien(d, oid, od, do, mnoznik, noc=False):
    for tab, kol in [("energia", "kwh"), ("przeplyw", "m3")]:
        df = d[tab]
        m = (df["obiekt_id"] == oid) & (df["czas"] >= pd.Timestamp(od, tz="UTC")) & (df["czas"] < pd.Timestamp(do, tz="UTC"))
        if noc:
            m &= df["czas"].dt.hour.between(0, 4)
        df.loc[m, kol] *= mnoznik


def _sucho(d, st, od, do):
    for tab, kol, filtr in [("pogoda", "opad_mm", d["pogoda"]["stacja"] == st), ("opad_ru", "mm", st == "RU")]:
        df = d[tab]
        m = filtr & (df["czas"] >= pd.Timestamp(od, tz="UTC")) & (df["czas"] < pd.Timestamp(do, tz="UTC"))
        df.loc[m, kol] = 0


def test_wykrywa_awarie_i_infiltracje(d):
    import copy
    from anomalie.uruchom import main
    d = copy.deepcopy(d)
    _zmien(d, "CH_T", "2025-06-10", "2025-06-12", 0.2)                              # awaria: spadek o 80%
    _sucho(d, "CH", "2025-06-07", "2025-06-12")
    _zmien(d, "RU_W", "2025-03-05", "2025-03-13", 1.6)                              # dopływ bez deszczu
    _zmien(d, "RU_W", "2025-03-05", "2025-03-13", 1.8, noc=True)
    _sucho(d, "RU", "2025-03-01", "2025-03-13")
    alarmy = pd.DataFrame([dict(obiekt_id="CH_T", czas=pd.Timestamp("2025-06-10 08:00", tz="UTC"), sygnal="awaria_P1", stan=1)])
    w = main(d=d, alarmy=alarmy, zapis_do_bazy=False)

    ch = w[(w["obiekt_id"] == "CH_T") & w["dzien"].between("2025-06-10", "2025-06-11")]
    assert (ch["anomalia"] == True).sum() == 2
    assert set(ch["typ"].dropna()) == {"spadek – awaria / przerwa"}

    ru = w[(w["obiekt_id"] == "RU_W") & w["dzien"].between("2025-03-06", "2025-03-12")]
    assert (ru["anomalia"] == True).mean() >= 0.7
    assert ru["typ"].dropna().str.contains("bez deszczu").all()

    assert ru["Odstaje_Od_Innych"].median() > 3                                    # tryb panelowy: odstaje od innych pompowni
    assert ru["Rodzaj_Anomalii"].dropna().str.contains("odstaje od innych").mean() >= 0.5

    a = w[w["anomalia"] == True]
    assert a["opis"].notna().all()
    assert a["glowna_cecha"].dropna().isin(SKUTKI).all()                            # przyczyna = skutek, nie pogoda
    assert 0 < len(a) / w["glosy"].notna().sum() < 0.1                             # rozsądny odsetek anomalii


def test_typ_zmiana_nastaw_sterowania():
    from anomalie.detekcja import typ_anomalii
    r = pd.Series(dict(nadwyzka_m3_proc=np.nan, residual_proc=3.0, opad_3d=0.0, topnienie_cm=0.0, temp_sr=10.0,
                       noc_udzial=np.nan, kwh_na_m3_wzgl=np.nan, nastawy_odchylenie_cm=15.0, glowna_cecha="poziom_max"))
    assert typ_anomalii(r) == "zmiana nastaw sterowania"
    assert typ_anomalii(r.copy().replace({15.0: 0.0})) == "inne / nietypowy dzień"          # zwykłe nastawy
    assert typ_anomalii(r.copy().replace({15.0: 0.0}).reindex([*r.index, "z_poziom_max"]).fillna({"z_poziom_max": 4.0})) \
        == "spiętrzenie w zbiorniku"                                                         # wysoki poziom, zwykłe nastawy


def test_dobor_odsetka_wybiera_lift_a_nie_skraj_siatki(monkeypatch):
    import anomalie.uruchom as u
    tabela = pd.DataFrame([dict(odsetek=o, model="zespół (≥2 z 3)", zlapane_wszystkie_proc=z, trafienia_przy_alarmie_proc=t,
                                lift=l) for o, z, t, l in [(0.03, 17, 80, 2.6), (0.05, 32, 79, 2.6), (0.08, 49, 74, 2.4),
                                                            (0.12, 60, 70, 2.2)]])
    monkeypatch.setattr(u, "walidacja_ch", lambda w, a, o: tabela[tabela["odsetek"] == o])
    monkeypatch.setattr(u, "wykryj_wszystkie", lambda dz, o: (None, None))
    monkeypatch.setattr(u, "ODSETKI", [0.03, 0.05, 0.08, 0.12])
    odsetek, _, powod = u.dobierz_odsetek(None, {"x": {1}})
    assert odsetek == 0.05 and "lift" in powod
