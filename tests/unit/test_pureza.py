"""Princípio III: a lógica de transição/decisão é pura (sem rede, SO, relógio global)."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parents[2] / "src" / "cato_monitor"
PROIBIDOS = {"requests", "os", "socket", "time", "subprocess", "threading", "logging"}
MODULOS_PUROS = ["transicoes.py", "motor.py", "cards.py", "snapshot.py"]


@pytest.mark.parametrize("arquivo", MODULOS_PUROS)
def test_modulo_puro(arquivo):
    arvore = ast.parse((SRC / arquivo).read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                assert alias.name.split(".")[0] not in PROIBIDOS, f"{arquivo} importa {alias.name}"
        elif isinstance(no, ast.ImportFrom) and no.level == 0:
            assert (no.module or "").split(".")[0] not in PROIBIDOS, f"{arquivo} importa de {no.module}"
        elif isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute):
            assert no.func.attr not in {"now", "utcnow", "today", "sleep", "monotonic"}, (
                f"{arquivo} usa relógio global ({no.func.attr})"
            )
