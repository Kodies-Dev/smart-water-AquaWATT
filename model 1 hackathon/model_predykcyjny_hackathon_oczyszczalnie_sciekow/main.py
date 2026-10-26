"""Model predykcyjny – hackathon oczyszczalnie ścieków (Smart Water Challenge).

Użycie:
    python main.py etl                       ładuje surowe dane z ../Dane do Postgresa
    python main.py model                     buduje i porównuje wszystkie warianty modeli
    python main.py model --warianty a,b      tylko wybrane warianty
    python main.py anomalie                  wykrywanie anomalii (zespół IF + LOF + One-Class SVM)
    python main.py raport [--model qwen3:8b] raport słowny o anomaliach (Ollama; bez niej – same fakty)
    python main.py prognoza --trenuj         trenuje model na wszystkich danych i zapisuje do modele/
    python main.py prognoza --plik X.csv     backtest na pliku + prognoza na kolejne 24 h (--obiekt, --stacja)
    python main.py aplikacja                 aplikacja w przeglądarce (Streamlit, na bazie Detektora Anomalii GUS)
    python main.py wszystko                  ETL, modele i anomalie po kolei
"""
import sys

TRYBY = ("etl", "model", "anomalie", "raport", "prognoza", "aplikacja", "wszystko")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TRYBY:
        print(__doc__)
        sys.exit(1)
    tryb, reszta = sys.argv[1], sys.argv[2:]
    if tryb == "aplikacja":
        import os
        import subprocess
        from pathlib import Path
        adres = os.environ.get("STREAMLIT_ADRES", "localhost")       # w Dockerze 0.0.0.0
        print(f"Aplikacja: http://localhost:8501  (Ctrl+C kończy)")
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py", "--server.address", adres,
                        "--server.port", "8501", *reszta], cwd=Path(__file__).resolve().parent / "aplikacja")
        return
    if tryb in ("etl", "wszystko"):
        from etl.main import main as etl
        etl()
    if tryb in ("model", "wszystko"):
        from model.eksperymenty import main as model
        model(reszta)
    if tryb == "prognoza":
        from model.prognoza import main as prognoza
        prognoza(reszta)
        return
    if tryb in ("anomalie", "wszystko"):
        from anomalie.uruchom import main as anomalie
        anomalie(reszta)
    if tryb in ("raport", "wszystko"):
        from anomalie.raport import main as raport
        raport(reszta if tryb == "raport" else [])


if __name__ == "__main__":
    main()
