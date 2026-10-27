"""Tryb prognozy: trening + zapis modelu, trzy formaty pliku dają ten sam wynik, backtest i prognoza na 24 h."""
import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def P(tmp_path_factory):
    import model.prognoza as P
    P.MODELE = tmp_path_factory.mktemp("modele")
    P.requests.get = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("test bez sieci"))
    return P


def _pliki(d, katalog):
    e = d["energia"][d["energia"]["obiekt_id"] == "RY_PZ1"]
    start = e["czas"].max() - pd.Timedelta(days=45)
    final = e[e["czas"] > start]
    d_hist = dict(d, energia=d["energia"][~((d["energia"]["obiekt_id"] == "RY_PZ1") & (d["energia"]["czas"] > start))])
    lok = final["czas"].dt.tz_convert("Europe/Warsaw")
    prosty = katalog / "PZ1_prosty.csv"
    pd.DataFrame({"czas": lok.dt.strftime("%Y-%m-%d %H:%M"), "kwh": final["kwh"]}).to_csv(prosty, sep=";", index=False)
    raport = katalog / "Rap_godzinowy - PZ1.csv"
    konc = (final["czas"] + pd.Timedelta(hours=1)).dt.tz_convert("Europe/Warsaw").dt.strftime("%d.%m.%Y %H:%M")
    pd.DataFrame({"Płatnik": "x", "PPE": "PPE:1", "Rodzaj": "Energia czynna pobrana", "Data": konc, "Strefa": "c",
                  "Wartość": final["kwh"].round(4).astype(str).str.replace(".", ","), "Kompletność": 100}) \
        .to_csv(raport, sep=";", index=False, encoding="cp1250")
    t = pd.date_range(start, final["czas"].max() + pd.Timedelta(hours=1), freq="15min")
    cum = np.interp(t.asi8, final["czas"].astype("int64").values, final["kwh"].cumsum().shift(fill_value=0).values) + 5e4
    l = t.tz_convert("Europe/Warsaw")
    licznik = katalog / "mock_zuzycie.csv"
    pd.DataFrame({"d": l.strftime("%Y-%m-%d"), "g": l.strftime("%H:%M:%S"), "t": "E", "w": cum.round(2),
                  "s": "Wartość z pomiaru"}).to_csv(licznik, sep=";", header=False, index=False)
    return d_hist, final, [prosty, raport, licznik]


def test_trening_zapis_i_prognoza(P, d, tmp_path):
    _, meta = P.trenuj(d)
    assert (P.MODELE / f"{P.WARIANT}.json").exists() and meta["drzew"] > 10
    d_hist, final, pliki = _pliki(d, tmp_path)
    wyniki = {}
    for p in pliki:
        nowe, rodzaj = P.wczytaj_plik(p)
        assert abs(nowe["kwh"].sum() / final["kwh"].sum() - 1) < 0.01, rodzaj          # wczytanie zgodne z oryginałem
        w, met, mies, jutro = P.uruchom("RY_PZ1", nowe, d=d_hist, pobierz_pogode=False, katalog=tmp_path / "wyniki")
        wyniki[rodzaj] = met["WAPE_doba"]
        assert len(jutro) == 24 and jutro["prognoza"].notna().all() and (jutro["prognoza"] > 0).all()
        nb = w[w["czas"] >= nowe["czas"].min()].dropna(subset=["rzeczywiste"])
        naiwny = (nb["rzeczywiste"].shift(24) - nb["rzeczywiste"]).abs().sum() / nb["rzeczywiste"].sum() * 100
        assert met["WAPE_h"] < naiwny                                                     # lepiej niż „wczoraj”
        p = met["porownanie_WAPE_doba"]                                                   # porównanie na tych samych dobach
        assert set(p) == {"model", "naiwny_doba", "naiwny_tydzien", "profil_4tyg"}
        assert p["model"] < min(p["naiwny_doba"], p["naiwny_tydzien"])
    assert set(wyniki) == {"prosty", "raport", "licznik"}
    assert max(wyniki.values()) - min(wyniki.values()) < 1.0                               # ten sam wynik z każdego formatu


def test_za_krotka_historia(P, d):
    nowe = pd.DataFrame({"czas": pd.date_range("2025-01-01", periods=24 * 10, freq="h", tz="UTC"), "kwh": 5.0})
    with pytest.raises(ValueError, match="Za mało danych"):
        P.dane_do_prognozy(d, "NOWY_OBIEKT", nowe, stacja="RY", pobierz_pogode=False)


def test_uczciwy_backtest_i_ostrzezenie(P, d, tmp_path):
    P.trenuj(d)                                                   # model widzi WSZYSTKO, także okres pliku
    _, final, pliki = _pliki(d, tmp_path)
    nowe, _ = P.wczytaj_plik(pliki[0])
    _, met_zwykly, _, _ = P.uruchom("RY_PZ1", nowe, d=d, pobierz_pogode=False, katalog=tmp_path / "w1")
    assert met_zwykly["widziane_w_treningu_proc"] > 90           # ostrzeżenie: plik był w treningu
    _, met_ucz, _, _ = P.uruchom("RY_PZ1", nowe, d=d, pobierz_pogode=False, katalog=tmp_path / "w2", uczciwie=True)
    assert met_ucz["uczciwie"] and met_ucz["widziane_w_treningu_proc"] == 0
    _, met_baza, _, jutro = P.uruchom("RY_PZ1", None, d=d, pobierz_pogode=False, katalog=tmp_path / "w3")
    assert met_baza == {} and len(jutro) == 24                   # bez pliku: brak (zawyżonego) backtestu
