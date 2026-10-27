# aplikacja/backend_ml_llm/ – warstwa obliczeniowa aplikacji

Jak w Detektorze GUS: moduły **bez Streamlita**, używane przez zakładki, ale dające się wywołać z notebooka czy skryptu.
Zasada z GUS: **wszystkie liczby liczy Python**, model językowy dostaje gotowe fakty i ma je tylko sformułować.

| Plik | Pochodzenie | Zawartość |
|---|---|---|
| `podsumowanie_klienta.py` | nowy | `podsumuj(prog, opis, d)` – wynik prognozy dla klienta: kafelki, **opis prostym językiem liczony w Pythonie** (polskie przecinki, dzień z największym błędem i opad tego dnia), `dzien_po_dniu()`, `excel()` – plik z 5 arkuszami |
| `raport_excel.py` | nowy | `raport_excel(...)` – raport .xlsx z natywnymi wykresami (jutro, dzień po dniu, miesiące, tydzień, plan P10–P90, pogoda) i formułami (sumy, WAPE, dni < 10%, SUMIFS / MAXIFS); sprawdzony przeliczeniem w LibreOffice: 0 błędów formuł |
| `raport_prognozy.py` | nowy (wzór: `report_generator`) | `fakty()` – fakty o modelu, teście i ostatniej prognozie; `raport()` i `pytanie()` – prompty dla Ollamy; `wczytaj_wyniki()`; nazwy wariantów po ludzku |
| `nasz_detektor.py` | nowy | adapter potoku anomalii (`anomalie/`) do formatu wyników `anomaly_d.py` z GUS (`Anomaly_IF`, `Anomaly_Final`, `Rodzaj_Anomalii`…) – dzięki temu oryginalne zakładki Raport / Pytanie działają bez zmian; `dane_z_bazy()` używane też przy starcie aplikacji |
| `mistral_raport_generator.py` | GUS | `report_generator`: `ask_mistral()` (Ollama, `OLLAMA_URL`), `build_row_facts()`, raport i pytania o anomalie |
| `desktop.py` | GUS | uruchomienie w natywnym oknie (pywebview) – opcjonalne |

Przykład z notebooka:
```python
import sys; sys.path[:0] = ["aplikacja", "."]
import model.prognoza as P
from backend_ml_llm.podsumowanie_klienta import podsumuj
nowe, rodzaj = P.wczytaj_plik(r"Dane\testowe\01_PZ1_8tyg_licznik_mock.csv")
prog = ("RY_PZ1",) + P.uruchom("RY_PZ1", nowe, uczciwie=True)
s, dz = podsumuj(prog, {"zrodlo": "01_PZ1...", "stacja": "RY"})
print(s["tekst"])
```

Model językowy: domyślnie `qwen3:8b` (`LLM_MODEL`), w aplikacji lista wszystkich zainstalowanych + polecane do pobrania
(Bielik 7B / 4.5B – polskie modele SpeakLeash). Tokeny `<think>` z qwen3 są usuwane.
