import os

import requests
import pandas as pd

# adres Ollamy - domyslnie lokalnie; w Dockerze ustawiany przez docker-compose (OLLAMA_URL)
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


class report_generator:

    #nie koniecznie mistral
    @staticmethod
    def ask_mistral(prompt: str, model: str = "mistral", timeout: int = 600) -> str:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["response"]

    @staticmethod
    def build_row_facts(df: pd.DataFrame, num_cols) -> str:
        """
        Cala analiza liczona w Pythonie (nie przez LLM) - dla kazdego wiersza-anomalii
        wskazuje najbardziej odstajaca kolumne (najwyzsze |zscore|), roznice od sredniej
        kroczacej i liczbe/nazwy modeli ktore zaglosowaly. LLM dostaje juz gotowe fakty
        i ma je tylko ladnie sformulowac po polsku - nie liczy nic sam.
        """
        anomalies_df = df[df['Anomaly_Final'] == 1]
        lines = []

        for idx, row in anomalies_df.iterrows():
            zscore_cols = {c: row[f'{c}_zscore'] for c in num_cols if f'{c}_zscore' in row} #z kazdego wiersz bierze kolumne i z score jej
            if not zscore_cols:
                continue
            main_col = max(zscore_cols, key=lambda c: abs(zscore_cols[c])) #znajduje najwiezkysz z score glowna przyczyne anomalii
            main_zscore = zscore_cols[main_col]
            main_diff_roll = row.get(f'{main_col}_diff_from_rolling_mean', 0)
            main_is_outlier = row.get(f'{main_col}_is_outlier', 0)

            votes = int(row['Anomaly_IF']) + int(row['Anomaly_LOF']) + int(row['Anomaly_SVM'])
            voted_by = []
            if row['Anomaly_IF'] == 1:
                voted_by.append("Isolation Forest")
            if row['Anomaly_LOF'] == 1:
                voted_by.append("LOF")
            if row['Anomaly_SVM'] == 1:
                voted_by.append("One-Class SVM")
            voted_str = ", ".join(voted_by) if voted_by else "brak"

            fact = (
                f"Wiersz {idx}: glowna przyczyna anomalii to kolumna '{main_col}' "
                f"(z-score={main_zscore:.2f}, roznica od sredniej kroczacej={main_diff_roll:.2f}, "
                f"flaga outlier IQR={'tak' if main_is_outlier == 1 else 'nie'}). "
                f"Wykryta przez {votes}/3 modeli: {voted_str}."
            )

            # tryb szeregow czasowych - dokladamy rodzaj anomalii
            if 'Rodzaj_Anomalii' in row:
                fact += (f" Rodzaj: {row['Rodzaj_Anomalii']} "
                         f"(nagla zmiana={row.get('Nagla_Zmiana', 0):.2f}, "
                         f"odstawanie od innych={row.get('Odstaje_Od_Innych', 0):.2f}).")

            if isinstance(row.get('opis'), str):
                fact += f" Opis z potoku anomalii: {row['opis']}"

            lines.append(fact)

        return "\n".join(lines)

    @staticmethod
    def generate_report(df: pd.DataFrame, model: str = "mistral") -> str:
        num_cols = [c for c in df.columns if f'{c}_zscore' in df.columns]

        if df['Anomaly_Final'].sum() == 0:
            return "Nie wykryto zadnych anomalii w danych."

        facts = report_generator.build_row_facts(df, num_cols)

        prompt = (
            "Pisz po polsku, zwykly tekst (nie tabela, nie markdown). "
            "Jestes neutralnym analitykiem danych.\n\n"
            "Ponizej sa JUZ GOTOWE, POLICZONE fakty o wierszach uznanych za anomalie. "
            "NIE zmieniaj zadnych liczb ani nazw kolumn/modeli - tylko sformuluj je "
            "w plynne, czytelne zdania po polsku, jeden akapit na wiersz. "
            "Nie dodawaj wlasnych obliczen ani interpretacji wykraczajacych poza podane fakty.\n\n"
            f"{facts}"
        )

        return report_generator.ask_mistral(prompt, model=model)

    @staticmethod
    def build_data_context(df: pd.DataFrame, num_cols=None, max_anom: int = 15) -> str:
        """
        Opis zbioru danych dla trybu pytan. Wszystkie liczby licza sie w pandasie,
        model dostaje je gotowe - dzieki temu nie zmysla statystyk.
        """
        czesci = []
        czesci.append(f"Liczba wierszy: {len(df)}")

        # kolumny zrodlowe, bez cech wyliczonych przez aplikacje
        sufiksy = ('_zscore', '_diff_mean', '_rolling_mean', '_rolling_std', '_diff_prev',
                   '_diff_from_rolling_mean', '_is_outlier', '_jump_score',
                   '_zscore_wlasny', '_zscore_miedzy')
        zrodlowe = [c for c in df.columns
                    if not c.endswith(sufiksy)
                    and c not in ('Anomaly_IF', 'Anomaly_LOF', 'Anomaly_SVM', 'Anomaly_Votes',
                                  'Anomaly_Final', 'Has_Outlier', 'Nagla_Zmiana',
                                  'Odstaje_Od_Innych', 'Rodzaj_Anomalii')]
        czesci.append(f"Kolumny zrodlowe: {', '.join(map(str, zrodlowe))}")

        liczbowe = df[zrodlowe].select_dtypes("number").columns.tolist()
        if liczbowe:
            czesci.append("\nStatystyki kolumn liczbowych:")
            opis = df[liczbowe].describe().T[['count', 'mean', 'std', 'min', '50%', 'max']]
            for kol, w in opis.iterrows():
                czesci.append(
                    f"  {kol}: srednia={w['mean']:.2f}, odch.std={w['std']:.2f}, "
                    f"min={w['min']:.2f}, mediana={w['50%']:.2f}, max={w['max']:.2f}"
                )

        braki = df[zrodlowe].isnull().sum()
        braki = braki[braki > 0]
        if len(braki) > 0:
            czesci.append("\nBraki danych: " + ", ".join(f"{k}={v}" for k, v in braki.items()))
        else:
            czesci.append("\nBraki danych: brak")

        if 'Anomaly_Final' in df.columns:
            n = int(df['Anomaly_Final'].sum())
            czesci.append(f"\nWykryte anomalie: {n} z {len(df)} wierszy "
                          f"({100 * n / max(len(df), 1):.1f} procent)")
            czesci.append(f"  Isolation Forest: {int(df['Anomaly_IF'].sum())}, "
                          f"LOF: {int(df['Anomaly_LOF'].sum())}, "
                          f"One-Class SVM: {int(df['Anomaly_SVM'].sum())}")

            if 'Rodzaj_Anomalii' in df.columns:
                czesci.append("  Rodzaje anomalii:")
                for rodzaj, ile in df[df['Anomaly_Final'] == 1]['Rodzaj_Anomalii'].value_counts().items():
                    czesci.append(f"    {rodzaj}: {ile}")

            if n > 0 and num_cols:
                czesci.append(f"\nNajsilniejsze anomalie (do {max_anom}):")
                top = (df[df['Anomaly_Final'] == 1]
                       .sort_values(['Anomaly_Votes', 'Has_Outlier'], ascending=False)
                       .head(max_anom))
                czesci.append(report_generator.build_row_facts(top, num_cols))

        return "\n".join(czesci)

    @staticmethod
    def ask_about_data(df: pd.DataFrame, question: str, num_cols=None,
                       model: str = "mistral", historia=None) -> str:
        """Pytanie uzytkownika o zbior danych. Model dostaje policzony kontekst."""
        kontekst = report_generator.build_data_context(df, num_cols)

        rozmowa = ""
        if historia:
            for pyt, odp in historia[-3:]:  # tylko ostatnie 3 pary, zeby nie rozdac kontekstu
                rozmowa += f"\nWczesniejsze pytanie: {pyt}\nTwoja odpowiedz: {odp}\n"

        prompt = (
            "Odpowiadasz po polsku, zwykly tekst. Jestes analitykiem danych i odpowiadasz "
            "na pytania o konkretny zbior danych.\n\n"
            "ZASADY:\n"
            "- Opieraj sie WYLACZNIE na podanych nizej faktach. Wszystkie liczby sa juz "
            "policzone - nie licz nic sacdm i nie zmieniaj podanych wartosci.\n"
            "- Jesli odpowiedzi nie da sie ustalic z podanych informacji, napisz wprost, "
            "ze tych danych tu nie ma. Nie zgaduj.\n"
            "- Odpowiadaj krotko i rzeczowo.\n\n"
            f"OPIS ZBIORU DANYCH:\n{kontekst}\n"
            f"{rozmowa}\n"
            f"PYTANIE: {question}"
        )

        return report_generator.ask_mistral(prompt, model=model)