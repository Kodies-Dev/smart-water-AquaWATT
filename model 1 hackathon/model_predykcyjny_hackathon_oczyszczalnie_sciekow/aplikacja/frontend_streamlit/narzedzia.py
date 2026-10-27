"""
Drobne funkcje pomocnicze używane w wielu miejscach, które nie pasują
nigdzie indziej - eksport do CSV, sprawdzanie Ollamy, próbkowanie
wykresów przy dużych zbiorach.
"""

import io
import os
import subprocess
import sys

import requests
import streamlit as st


class Narzedzia:
    """Zbiorka funkcji bez własnego stanu - stąd staticmethod wszędzie,
    tak samo jak w anomaly_d.py i mistral_raport_generator.py."""

    @staticmethod
    def to_csv_bytes(df):
        buf = io.StringIO()  # wirtualny plik tekstowy
        df.to_csv(buf, index=False)
        return buf.getvalue().encode("utf-8")  # zamienia na surowe bajty
        # TODO zapytac sie kierownika czy moze byc ten utf-8 bo windows-1250

    @staticmethod
    def get_ollama_models():
        """llmowskie guano - tutaj mamy podgląd jakie modele sa dostępne lokalnie"""
        try:
            # TODO pobawic sie modelami, moze jakis excel - bawic sie tym potem
            r = requests.get(f"{os.environ.get('OLLAMA_URL', 'http://localhost:11434')}/api/tags", timeout=3)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]  # wraca po prostu wszystkie dostepne modele
        except Exception:
            return []

    @staticmethod
    def downsample(df, max_points=None):
        """Co n-ty wiersz, żeby wykres liniowy pozostal czytelny i szybki.
        Limit 0 (domyślnie) oznacza brak próbkowania - rysowane sa wszystkie punkty."""
        if max_points is None:
            max_points = st.session_state.get("limit_punktow", 0)
        if not max_points or len(df) <= max_points:
            return df, 1
        step = len(df) // max_points + 1
        return df.iloc[::step], step  # ma skakac co step wiersz, przydaje sie w szczegolnosci
        # do rollbackow sredniej kroczacej itp

    @staticmethod
    def domyslny_katalog():
        """Folder, do którego domyślnie zapisujemy pliki. Pobrane u większości
        ludzi istnieje, więc zaczynamy od niego."""
        pobrane = os.path.join(os.path.expanduser("~"), "Downloads")
        return pobrane if os.path.isdir(pobrane) else os.path.expanduser("~")

    @staticmethod
    def zapisz_plik(dane, nazwa, katalog):
        """Zapisuje bajty na dysk. Zwraca (czy_się_udało, komunikat)."""
        try:
            katalog = os.path.expanduser(katalog.strip())
            if not os.path.isdir(katalog):
                return False, f"Katalog nie istnieje: {katalog}"
            sciezka = os.path.join(katalog, nazwa)
            with open(sciezka, "wb") as f:
                f.write(dane)
            return True, sciezka
        except PermissionError:
            return False, "Brak uprawnień do zapisu w tym katalogu."
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    @staticmethod
    def _bez_okna_konsoli():
        """
        Dodatkowe argumenty dla subprocess, żeby na Windowsie nie mignęło czarne
        okno konsoli przy uruchamianiu PowerShella. Na pozostałych systemach
        zwraca pusty słownik - tam problem nie występuje.
        """
        if sys.platform != "win32":
            return {}
        # CREATE_NO_WINDOW dziala od Pythona 3.7; STARTUPINFO to zabezpieczenie
        # na wypadek, gdyby sama flaga nie wystarczyla w danym srodowisku
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE
        return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": info}

    @staticmethod
    def okno_zapisu(nazwa_domyslna):
        """
        Natywne okno "Zapisz jako" - użytkownik wskazuje folder I nazwę pliku naraz.
        Zwraca (pełna_ścieżka, komunikat_błędu). Anulowanie daje (None, None).

        Dialog uruchamiany jest jako OSOBNY PROCES, który ma własny watek główny.
        To omija problem, przez który okno systemowe wywołane prosto z kodu aplikacji
        zawiesza się na macOS - tam okna muszą powstawać na watku głównym, a ten jest
        zajęty przez okno aplikacji.

        Korzystamy z narzędzi wbudowanych w system, bez dodatkowych zależności:
        osascript na macOS, PowerShell na Windows, zenity albo kdialog na Linuksie.
        """
        try:
            if sys.platform == "darwin":
                skrypt = (
                    'tell application "System Events" to activate\n'
                    f'set plik to choose file name with prompt "Zapisz plik" '
                    f'default name "{nazwa_domyslna}"\n'
                    'POSIX path of plik'
                )
                r = subprocess.run(["osascript", "-e", skrypt],
                                   capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    # AppleScript zawsze zwraca kod -128 przy anulowaniu, niezaleznie
                    # od jezyka systemu - szukanie tekstu bylo bledem, bo po polsku
                    # brzmi to inaczej niz po angielsku
                    if "(-128)" in r.stderr:
                        return None, None
                    return None, r.stderr.strip()
                return r.stdout.strip(), None

            if sys.platform == "win32":
                ps = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$d = New-Object System.Windows.Forms.SaveFileDialog; "
                    f"$d.FileName = '{nazwa_domyslna}'; "
                    "$d.Filter = 'Wszystkie pliki|*.*'; "
                    "$d.OverwritePrompt = $true; "
                    "if ($d.ShowDialog() -eq 'OK') { Write-Output $d.FileName }"
                )
                r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                                   capture_output=True, text=True, timeout=300,
                                   **Narzedzia._bez_okna_konsoli())
                sciezka = r.stdout.strip()
                return (sciezka, None) if sciezka else (None, None)

            # Linux - zenity albo kdialog, zaleznie od tego co jest zainstalowane
            for polecenie in (["zenity", "--file-selection", "--save",
                               "--confirm-overwrite", f"--filename={nazwa_domyslna}"],
                              ["kdialog", "--getsavefilename", nazwa_domyslna]):
                try:
                    r = subprocess.run(polecenie, capture_output=True, text=True, timeout=300)
                    sciezka = r.stdout.strip()
                    return (sciezka, None) if sciezka else (None, None)
                except FileNotFoundError:
                    continue
            return None, "Brak narzędzia do wyboru pliku (zainstaluj zenity albo kdialog)."

        except subprocess.TimeoutExpired:
            return None, "Okno zapisu nie zostało zamknięte w ciągu 5 minut."
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"

    @staticmethod
    def tryb_desktopowy():
        """Czy aplikacja działa w oknie desktopowym (pywebview), a nie w przeglądarce.
        Znacznik ustawia desktop.py przed uruchomieniem serwera."""
        return os.environ.get("DETEKTOR_DESKTOP") == "1"

    @staticmethod
    def przycisk_pobierania(etykieta, dane, nazwa_pliku, mime, key):
        """
        Zapisanie pliku - inaczej w przeglądarce, inaczej w oknie desktopowym.

        st.download_button korzysta z mechanizmu pobierania PRZEGLĄDARKI. W oknie
        aplikacji (pywebview) osadzona przeglądarka tego nie obsługuje i zamiast
        zapisać plik PRZEKIEROWUJE OKNO pod adres z danymi - aplikacja znika
        z ekranu, a zostaje surowa treść pliku. Dlatego w trybie desktopowym ten
        przycisk jest całkowicie ukryty, a plik zapisuje bezpośrednio Python.
        """
        if not Narzedzia.tryb_desktopowy():
            # przegladarka - zwykle pobieranie dziala normalnie
            st.download_button(etykieta, dane, file_name=nazwa_pliku,
                               mime=mime, key=f"{key}_dl")
            return

        # Okno desktopowe - jeden przycisk: wybor miejsca i zapis w jednym kroku.
        # Uzytkownik wskazuje folder oraz nazwe pliku w natywnym oknie systemowym,
        # a plik zapisuje sie od razu po zatwierdzeniu.
        if st.button(etykieta, key=f"{key}_btn", type="primary"):
            sciezka, blad = Narzedzia.okno_zapisu(nazwa_pliku)

            if blad:
                st.error(blad)
            elif sciezka:
                katalog = os.path.dirname(sciezka)
                plik = os.path.basename(sciezka)
                ok, info = Narzedzia.zapisz_plik(dane, plik, katalog)
                if ok:
                    st.success(f"Zapisano: {info}")
                else:
                    st.error(info)
            # sciezka pusta i brak bledu = uzytkownik anulowal, nie robimy nic