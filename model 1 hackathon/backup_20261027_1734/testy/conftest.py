"""Wspólne ustawienia testów: ścieżka projektu, wyniki do folderu tymczasowego, dane syntetyczne."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("WYNIKI_DIR", tempfile.mkdtemp(prefix="wyniki_testy_"))

import pytest  # noqa: E402

from testy.syntetyczne import dane  # noqa: E402


@pytest.fixture(scope="session")
def d():
    """Syntetyczne dane w formacie tabel z bazy (bez bazy): rytm dobowy, dni wolne, sezon, reakcja na deszcz, szum."""
    return dane()
