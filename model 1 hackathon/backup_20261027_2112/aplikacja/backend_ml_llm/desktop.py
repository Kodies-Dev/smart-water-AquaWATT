import os
import socket
import subprocess
import sys
import threading
import time

import requests
import webview

TYTUL = "Detektor anomalii"


def znajdz_wolny_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def czekaj_na_serwer(url, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        try:
            if requests.get(url, timeout=1).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.4)
    return False


def katalog_aplikacji():
    """Katalog, w ktorym lezy app.py wraz z folderami frontend_streamlit,
    backend_ml_llm i .streamlit.

    W wersji spakowanej wszystko laduje w katalogu tymczasowym _MEIPASS.
    W wersji zwyklej ten plik siedzi w backend_ml_llm/, wiec app.py jest
    o jeden poziom WYZEJ - stad dirname(dirname(...)).
    """
    if getattr(sys, "_MEIPASS", None):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def start_streamlit_w_procesie(app_path, port):
    """
    Tryb spakowany (PyInstaller). NIE wolno tu uzyc subprocess z sys.executable,
    bo w binarce sys.executable wskazuje na sama aplikacje - uruchomilaby sie
    w nieskonczonej petli zamiast Streamlita. Dlatego serwer startuje w watku,
    wewnatrz tego samego procesu.
    """
    import signal

    # Znacznik dla aplikacji: dzialamy w oknie desktopowym, a nie w przegladarce.
    # Wbudowana przegladarka nie obsluguje pobierania plikow - klikniecie przycisku
    # pobierania przekierowuje okno pod adres z danymi i aplikacja znika z ekranu.
    # Po tym znaczniku interfejs wie, ze ma pokazac zapis na dysk zamiast pobierania.
    os.environ["DETEKTOR_DESKTOP"] = "1"

    import streamlit.web.bootstrap as bootstrap
    from streamlit import config as st_config

    st_config.set_option("server.port", port)
    st_config.set_option("server.headless", True)
    st_config.set_option("browser.gatherUsageStats", False)
    st_config.set_option("server.fileWatcherType", "none")
    st_config.set_option("global.developmentMode", False)

    def uruchom():
        # bootstrap.run instaluje obsluge SIGTERM, a signal.signal dziala tylko
        # na glownym watku - bez tego podmienienia serwer nie wstanie w watku
        oryginalny = signal.signal
        signal.signal = lambda *a, **k: None
        try:
            bootstrap.run(app_path, False, [], {})
        finally:
            signal.signal = oryginalny

    watek = threading.Thread(target=uruchom, daemon=True)
    watek.start()
    return None  # brak procesu do ubicia, watek jest daemonem


def start_streamlit_podprocesem(app_path, port):
    """Tryb zwykly - Streamlit jako osobny proces."""
    # ten sam znacznik co wyzej, tyle ze przekazany do procesu potomnego
    srodowisko = dict(os.environ, DETEKTOR_DESKTOP="1")
    return subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", app_path,
            "--server.port", str(port),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
            "--server.fileWatcherType", "none",
            "--global.developmentMode", "false",
        ],
        env=srodowisko,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    port = znajdz_wolny_port()
    url = f"http://localhost:{port}"

    base_dir = katalog_aplikacji()
    app_path = os.path.join(base_dir, "app.py")

    # config.toml musi byc widoczny dla Streamlita - szuka go w katalogu roboczym
    os.chdir(base_dir)

    spakowane = getattr(sys, "frozen", False)
    proc = (start_streamlit_w_procesie(app_path, port) if spakowane
            else start_streamlit_podprocesem(app_path, port))

    try:
        if not czekaj_na_serwer(url):
            print("Nie udalo sie uruchomic serwera Streamlit.")
            return

        webview.create_window(
            TYTUL,
            url,
            width=1400,
            height=900,
            min_size=(1000, 700),
        )
        webview.start()
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()


if __name__ == "__main__":
    main()