"""Raport słowny o anomaliach dla dyspozytora – na wzór report_generator z Detektora Anomalii (GUS).
Kluczowa zasada (z testów w tamtym projekcie): WSZYSTKIE liczby liczy Python, model językowy dostaje gotowe fakty
i ma je tylko sformułować w zdania. Bez Ollamy raport też powstaje – jako uporządkowane fakty.
Uruchom:  python main.py raport [--model qwen3:8b] [--top 5]"""
import argparse
import re
from datetime import date

import pandas as pd
import requests

from .ustawienia import WYNIKI, OLLAMA_URL, LLM_MODEL


def zapytaj_llm(prompt, model=LLM_MODEL, timeout=600):
    r = requests.post(f"{OLLAMA_URL}/api/generate", json={"model": model, "prompt": prompt, "stream": False}, timeout=timeout)
    r.raise_for_status()
    return re.sub(r"<think>.*?</think>", "", r.json()["response"], flags=re.S).strip()   # qwen3 dokleja tok myślenia


def fakty(top=5):
    """Wszystkie liczby raportu – policzone tutaj, z plików wynikowych anomalii."""
    dni = pd.read_csv(WYNIKI / "dni.csv", parse_dates=["dzien"])
    rank = pd.read_csv(WYNIKI / "ranking.csv")
    anom = dni[dni["anomalia"] == True]
    linie = ["PODSUMOWANIE",
             f"Ocenionych dób: {int(dni['glosy'].notna().sum())}, anomalii: {len(anom)} "
             f"({100 * len(anom) / max(dni['glosy'].notna().sum(), 1):.1f}%). Anomalia = co najmniej 2 z 3 modeli "
             f"(Isolation Forest, LOF, One-Class SVM).",
             f"Okres: {dni['dzien'].min():%Y-%m-%d} – {dni['dzien'].max():%Y-%m-%d}."]
    p = WYNIKI / "walidacja_CH.csv"
    if p.exists():
        w = pd.read_csv(p)
        z = w[w["model"].str.startswith("zespół")].dropna(subset=["lift"]).sort_values("lift", ascending=False).head(1)
        if len(z):
            r = z.iloc[0]
            linie.append(f"Walidacja na alarmach tłoczni w Chorzowie: zespół wskazuje doby przy alarmach "
                         f"{r['lift']:.1f} razy częściej niż losowy wybór dni; złapał {r['zlapane_wszystkie_proc']:.0f}% dni z alarmem.")
        elif len(w):
            linie.append("Walidacja na alarmach tłoczni w Chorzowie: zespół nie wskazał dób przy alarmach.")
    linie.append("\nRANKING OBIEKTÓW (wody obce)")
    for _, r in rank.iterrows():
        cz = [f"{r['obiekt']}: {int(r['anomalii'])} anomalii"]
        if pd.notna(r.get("udzial_wod_obcych_proc")):
            cz.append(f"wody obce {r['udzial_wod_obcych_proc']:.1f}% przepływu")
        if pd.notna(r.get("reakcja_m3_na_mm")):
            cz.append(f"{r['reakcja_m3_na_mm']:.0f} m³ wód obcych na 1 mm deszczu")
        if pd.notna(r.get("nadwyzka_energii_proc")):
            cz.append(f"energia ponad bazę bezdeszczową {r['nadwyzka_energii_proc']:.1f}%")
        linie.append(", ".join(cz) + ".")
    linie.append("\nTYPY ANOMALII PER OBIEKT")
    for oid, g in anom.groupby("obiekt_id"):
        linie.append(f"{oid}: " + ", ".join(f"{t} – {n}" for t, n in g["typ"].value_counts().items()) + ".")
    linie.append(f"\nNAJWIĘKSZE ANOMALIE (do {top} na obiekt)")
    for oid, g in anom.groupby("obiekt_id"):
        g = g.assign(s=g["skala_m3"].abs().fillna(g["skala_kwh"].abs())).sort_values("s", ascending=False).head(top)
        linie += [f"- {o}" for o in g["opis"]]
    return "\n".join(linie)


def raport(model=LLM_MODEL, top=5):
    f = fakty(top)
    prompt = ("Piszesz po polsku, zwykły tekst bez tabel i bez markdown. Jesteś analitykiem przedsiębiorstwa wodociągowo-"
              "kanalizacyjnego i piszesz krótki raport dla dyspozytora sieci kanalizacyjnej.\n\n"
              "Poniżej są JUŻ POLICZONE fakty o anomaliach. ZASADY:\n"
              "- NIE zmieniaj żadnych liczb, dat, nazw obiektów ani typów anomalii – tylko sformułuj je w zdania.\n"
              "- Nie licz nic sam i nie dodawaj faktów spoza listy.\n"
              "- Struktura: 1) podsumowanie w 2–3 zdaniach, 2) akapit na każdy obiekt, "
              "3) na końcu 2–3 zalecenia wynikające WPROST z faktów (np. który obiekt sprawdzić pod kątem infiltracji).\n\n"
              f"FAKTY:\n{f}")
    try:
        tekst, zrodlo = zapytaj_llm(prompt, model), f"model językowy {model} (Ollama)"
    except Exception as e:
        tekst, zrodlo = f, f"bez modelu językowego – Ollama niedostępna ({type(e).__name__}); poniżej same fakty"
    md = (f"# Raport anomalii – sieć kanalizacyjna\n\n*{date.today():%d.%m.%Y} · {zrodlo}*\n\n{tekst}\n\n"
          f"---\n\n## Fakty źródłowe (policzone w Pythonie)\n\n```\n{f}\n```\n")
    (WYNIKI / "raport.md").write_text(md, encoding="utf-8")
    return md, zrodlo


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=LLM_MODEL)
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args(argv)
    if not (WYNIKI / "dni.csv").exists():
        raise SystemExit("Najpierw uruchom: python main.py anomalie")
    md, zrodlo = raport(a.model, a.top)
    print(f"Raport: {WYNIKI / 'raport.md'} ({zrodlo})\n")
    print(md[:3000])


if __name__ == "__main__":
    main()
