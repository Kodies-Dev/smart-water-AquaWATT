import matplotlib.pyplot as plt
import pandas as pd
"""wykresy nie z plottib motem TODO zmien na seaborna jak bedziesz mial czas ale na razie nie uzywane
"""

class anomaly_visualizer:

    @staticmethod
    def plot_rolling(df: pd.DataFrame, col: str, save_path: str = None):
        """srednia korczaca do testow"""
        fig, ax = plt.subplots(figsize=(12, 5))

        ax.plot(df.index, df[col], label=col, color="steelblue")
        ax.plot(df.index, df[f'{col}_rolling_mean'], label="srednia kroczaca", color="orange", linestyle="--")

        anomalies = df[df['Anomaly_Final'] == 1]
        ax.scatter(anomalies.index, anomalies[col], color="red", label="anomalia", zorder=5)

        ax.set_title(f"{col} - wartosc vs srednia kroczaca")
        ax.set_xlabel("indeks wiersza")
        ax.set_ylabel(col)
        ax.legend()
        fig.tight_layout()

        if save_path:
            fig.savefig(save_path)

        plt.close(fig)
        return fig

    @staticmethod
    def plot_zscore(df: pd.DataFrame, col: str, threshold: float = 3.0, save_path: str = None):
        """Z-score kolumny w czasie, z liniami progowymi i zaznaczonymi anomaliami."""
        fig, ax = plt.subplots(figsize=(12, 5))

        zscore_col = f'{col}_zscore'
        ax.scatter(df.index, df[zscore_col], color="steelblue", label="z-score")

        anomalies = df[df['Anomaly_Final'] == 1]
        ax.scatter(anomalies.index, anomalies[zscore_col], color="red", label="anomalia", zorder=5)

        ax.axhline(threshold, color="gray", linestyle="--", label=f"prog +/-{threshold}")
        ax.axhline(-threshold, color="gray", linestyle="--")

        ax.set_title(f"{col} - z-score")
        ax.set_xlabel("indeks wiersza")
        ax.set_ylabel("z-score")
        ax.legend()
        fig.tight_layout()

        if save_path:
            fig.savefig(save_path)

        plt.close(fig)
        return fig

    @staticmethod
    def plot_model_votes(df: pd.DataFrame, save_path: str = None):
        """Ile wierszy wykryl kazdy model (IF, LOF, SVM, Final)."""
        fig, ax = plt.subplots(figsize=(8, 5))

        counts = {
            "Isolation Forest": df['Anomaly_IF'].sum(),
            "LOF": df['Anomaly_LOF'].sum(),
            "One-Class SVM": df['Anomaly_SVM'].sum(),
            "Final (ensemble)": df['Anomaly_Final'].sum(),
        }

        ax.bar(counts.keys(), counts.values(), color=["steelblue", "steelblue", "steelblue", "red"])
        ax.set_title("Liczba wykrytych anomalii per model")
        ax.set_ylabel("liczba wierszy")
        fig.tight_layout()

        if save_path:
            fig.savefig(save_path)

        plt.close(fig)
        return fig

    @staticmethod
    def plot_outlier_heatmap(df: pd.DataFrame, num_cols, save_path: str = None):
        """Heatmapa flag is_outlier - ktore kolumny/wiersze najczesciej odstaja."""
        outlier_cols = [f'{c}_is_outlier' for c in num_cols if f'{c}_is_outlier' in df.columns]
        data = df[outlier_cols]

        fig, ax = plt.subplots(figsize=(10, max(4, len(df) * 0.25)))
        im = ax.imshow(data.values, aspect="auto", cmap="Reds", vmin=0, vmax=1)

        ax.set_xticks(range(len(outlier_cols)))
        ax.set_xticklabels([c.replace('_is_outlier', '') for c in outlier_cols], rotation=45, ha="right")
        ax.set_yticks(range(len(df)))
        ax.set_yticklabels(df.index)
        ax.set_title("Flagi outlierow (IQR) per wiersz i kolumna")
        fig.colorbar(im, ax=ax, label="is_outlier")
        fig.tight_layout()

        if save_path:
            fig.savefig(save_path)

        plt.close(fig)
        return fig