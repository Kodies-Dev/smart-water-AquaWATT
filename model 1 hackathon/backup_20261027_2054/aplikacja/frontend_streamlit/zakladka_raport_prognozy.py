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
        st.warning(f"Nie wykryto Ollamy ({OLLAMA_URL}). Uruchom `ollama serve`. Bez niej ponizej widac same policzone fakty.")
    opcje = zainstalowane + [m for m in POLECANE if m not in zainstalowane and f"{m}:latest" not in zainstalowane]
    etykieta = lambda m: m if m in zainstalowane else f"{m}   (do pobrania)"
    pomoc = (f"Zainstalowane w Ollamie: {len(zainstalowane)}. Mozna tez wpisac dowolna nazwe modelu z ollama.com "
             f"albo hf.co/... (GGUF z Hugging Face).")
    try:
        model = st.selectbox("Model", opcje, format_func=etykieta, key=key, help=pomoc, accept_new_options=True)
    except TypeError:                                              # starszy Streamlit bez accept_new_options
        model = st.selectbox("Model", opcje, format_func=etykieta, key=key, help=pomoc)
    if dziala and model and model not in zainstalowane:
        st.info(f"Model `{model}` nie jest zainstalowany w Ollamie.")
        if st.button(f"Pobierz {model}", key=f"{key}_pull"):
            with st.spinner(f"Pobieram {model} - kilka GB, moze potrwac kilka minut..."):
                try:
                    r = requests.post(f"{OLLAMA_URL}/api/pull", json={"model": model, "stream": False}, timeout=7200)
                    r.raise_for_status()
                    st.success(f"Pobrano {model}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Nie udalo sie pobrac: {e}")
    return model


def renderuj():
    st.subheader("Raport o prognozie")
    prog = st.session_state.get("prog_wynik")
    if prog is not None:
        from frontend_streamlit.zakladka_twoja_prognoza import pokaz_podsumowanie
        st.caption("Podsumowanie poniżej jest liczone i pisane w Pythonie - liczby są zawsze poprawne.")
        pokaz_podsumowanie(prog, st.session_state.get("prog_opis", {}), st.session_state.get("d_baza"), klucz="rap")
        st.divider()
    else:
        st.info("Zrób prognozę w zakładce 'Prognoza' - tutaj pojawi się jej podsumowanie z plikami do pobrania.")
    st.markdown("#### Raport opisowy (lokalny model językowy)")
    st.caption("Model językowy formułuje tekst z faktów policzonych w Pythonie. Może się czasem pomylić w sformułowaniach - "
               "liczby sprawdzisz w faktach poniżej i w podsumowaniu wyżej.")
    meta, met, _, _ = wczytaj_wyniki()
    f = fakty(meta, met, st.session_state.get("prog_wynik"))
    if not f.strip():
        st.info("Brak wynikow - uruchom `python main.py model` albo zrob prognoze w zakladce 'Prognoza'.")
        return

    model = _modele_llm("model_raport_prog")
    with st.expander("Fakty, ktore dostaje model (policzone w Pythonie)"):
        st.text(f)
    if st.button("Generuj raport", type="primary"):
        with st.spinner(f"Model pisze raport ({model})..."):
            try:
                st.session_state.raport_prognozy = raport(f, model)
            except Exception as e:
                st.error(f"Blad generowania raportu: {e}")
    if st.session_state.get("raport_prognozy"):
        st.markdown("#### Raport")
        st.write(st.session_state.raport_prognozy)
        tekst = st.session_state.raport_prognozy + "\n\n---\nFAKTY ZRODLOWE\n" + f
        Narzedzia.przycisk_pobierania("Pobierz raport (TXT)", tekst.encode("utf-8"), "raport_prognoza.txt",
                                      "text/plain", key="pob_raport_prog")
