"""HEALTHCHECK do contêiner: `python -m cato_monitor.healthcheck`.

Saúde = idade de `${STATE_DIR}/last_cycle` ≤ 3 × INTERVALO + 30 s. Um ciclo em que a Cato falhou
ainda conta como concluído (o laço está vivo); a falha da Cato é avisada pelo próprio monitor.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .estado_store import NOME_LAST_CYCLE
from .modelos import str_para_ts


def saudavel(state_dir: Path, intervalo_segundos: int, agora: datetime) -> bool:
    try:
        ultimo = str_para_ts(Path(state_dir, NOME_LAST_CYCLE).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    idade = (agora - ultimo).total_seconds()
    return idade <= 3 * intervalo_segundos + 30


def main() -> int:
    state_dir = Path(os.environ.get("STATE_DIR") or "/data")
    try:
        intervalo = int(os.environ.get("INTERVALO_SEGUNDOS") or 60)
    except ValueError:
        intervalo = 60
    return 0 if saudavel(state_dir, intervalo, datetime.now(timezone.utc)) else 1


if __name__ == "__main__":
    sys.exit(main())
