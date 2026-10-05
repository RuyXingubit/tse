import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def carregar():
    def _carregar(nome: str) -> dict:
        return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))

    return _carregar
