"""
Zakladka Raport - raport o prognozie energii pisany przez lokalny LLM (Ollama) z faktow policzonych w Pythonie:
zapisany model, wyniki eksperymentow i ostatnia prognoza z zakladki Prognoza.
"""

import os

import requests
import streamlit as st

from backend_ml_llm.raport_prognozy import fakty, raport, wczytaj_wyniki
from frontend_streamlit.narzedzia import Narzedzia

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
# polecane do pobrania - Bielik (SpeakLeash, polski) najlepiej pisze po polsku; nazwy jak w `ollama pull`
POLECANE = ["qwen3:8b", "hf.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q4_K_M",
            "hf.co/speakleash/Bielik-4.5B-v3.0-Instruct-GGUF:Q8_0", "llama3.1:8b", "gemma3:12b", "mistral-nemo", "mistral"]


def _ollama_dziala():
    try:
        return requests.get(f"{OLLAMA_URL}/api/tags", timeout=3).ok
    except Exception:
        return False


def _modele_llm(key):
    """Wybor modelu: wszystkie zainstalowane w Ollamie + polecane do pobrania + dowolna wpisana nazwa.
    Model, ktorego nie ma lokalnie, mozna pobrac przyciskiem (ollama pull)."""
    dziala = _ollama_dziala()
    zainstalowane = Narzedzia.get_ollama_models() if dziala else []
    if not dziala:
        st.warning(f"Lokalny model językowy (Ollama) jest niedostępny pod adresem {OLLAMA_URL}. "
                   f"Generowanie raportu AI jest wyłączone; poniżej wyświetlane są wyłącznie fakty wyliczone z danych.")
    opcje = zainstalowane + [m for m in POLECANE if m not in zainstalowane and f"{m}:latest" not in zainstalowane]
    etykieta = lambda m: m if m in zainstalowane else f"{m}   (do pobrania)"
    pomoc = (f"Zainstalowane w Ollamie: {len(zainstalowane)}. Mozna tez wpisac dowolna nazwe modelu z ollama.com "
             f"albo hf.co/... (GGUF z Hugging Face).")
    try:
        model = st.selectbox("Model", opcje, format_func=etykieta, key=key, help=pomoc, accept_new_options=True)
    except TypeError:                                              # starszy Streamlit bez accept_new_options
        model = st.selectbox("Model", opcje, format_func=etykieta, key=key, help=pomoc)
    if dziala and model and model not in zainstalowane:
        st.info(f"Model `{model}` nie jest zainstalowany w Ollamie. Można go pobrać poniżej.")
        if st.button(f"Pobierz {model}", key=f"{key}_pull"):
            with st.spinner(f"Pobieranie modelu {model} (kilka GB)..."):
                try:
                    r = requests.post(f"{OLLAMA_URL}/api/pull", json={"model": model, "stream": False}, timeout=7200)
                    r.raise_for_status()
                    st.success(f"Model {model} został pobrany.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Nie udało się pobrać modelu: {e}")
    return model


def renderuj():
    st.subheader("Raport o prognozie")
    prog = st.session_state.get("prog_wynik")
    if prog is not None:
        from frontend_streamlit.zakladka_twoja_prognoza import pokaz_podsumowanie
        pokaz_podsumowanie(prog, st.session_state.get("prog_opis", {}), st.session_state.get("d_baza"), klucz="rap")
        st.divider()
    else:
        st.info("Raport wymaga wcześniejszego przygotowania prognozy w zakładce **Prognoza**.")
    st.markdown("#### Raport AI (lokalny LLM)")
    st.caption("Tekst z faktów policzonych w Pythonie – liczby sprawdzisz w faktach poniżej.")
    meta, met, _, _ = wczytaj_wyniki()
    f = fakty(meta, met, st.session_state.get("prog_wynik"))
    if not f.strip():
        st.info("Brak danych do raportu. Przygotuj prognozę w zakładce **Prognoza**.")
        return

    model = _modele_llm("model_raport_prog")
    with st.expander("Fakty dla modelu"):
        st.text(f)
    if st.button("Generuj raport", type="primary"):
        with st.spinner(f"Generowanie raportu ({model})..."):
            try:
                st.session_state.raport_prognozy = raport(f, model)
            except Exception as e:
                st.error(f"Błąd generowania raportu: {e}")
    if st.session_state.get("raport_prognozy"):
        st.markdown("#### Raport")
        st.write(st.session_state.raport_prognozy)
        tekst = st.session_state.raport_prognozy + "\n\n---\nFAKTY ZRODLOWE\n" + f
        Narzedzia.przycisk_pobierania("Pobierz raport (TXT)", tekst.encode("utf-8"), "raport_prognoza.txt",
                                      "text/plain", key="pob_raport_prog")
