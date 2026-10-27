"""Ustawienia eksperymentów."""
import os
from pathlib import Path

from etl.config import DB_URL   # jedno miejsce na połączenie z bazą (etl/config.py)

WYNIKI = Path(os.environ.get("WYNIKI_DIR", Path(__file__).resolve().parents[1] / "wyniki"))
TZ = "Europe/Warsaw"

H = 24            # wyprzedzenie prognozy [h]: prognoza na następną dobę – cechy znane 24 h wcześniej
PODZIAL = 0.70    # chronologicznie, per obiekt: pierwsze 70% czasu = trening, ostatnie 30% = test
WALIDACJA = 0.15  # końcówka treningu (per obiekt) do early stopping XGBoost
MOKRY_DZIEN_MM = 1.0  # doba z opadem > 1 mm = „mokra” (osobne metryki)

# Cel modelu: log(1 + kWh / poziom obiektu) – spłaszcza szczyty po ulewach.
# Strata absolutna = model celuje w medianę, zgodnie z metryką WAPE (średnia przy szczytach jest zawyżona).
XGB = dict(n_estimators=3000, learning_rate=0.03, max_depth=6, min_child_weight=10,
           subsample=0.8, colsample_bytree=0.8, tree_method="hist",
           objective="reg:absoluteerror", early_stopping_rounds=200)
