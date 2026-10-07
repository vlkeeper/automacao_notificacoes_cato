"""Relógio injetável: a lógica de negócio nunca lê a hora do sistema diretamente."""

from datetime import datetime, timezone
from typing import Protocol


class Relogio(Protocol):
    def agora(self) -> datetime:
        """Momento atual como datetime aware em UTC."""
        ...


class RelogioSistema:
    def agora(self) -> datetime:
        return datetime.now(timezone.utc)
