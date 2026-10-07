"""Logs JSON (uma linha por registro) com redação de segredos."""

from __future__ import annotations

import json
import logging
import re
import sys
import traceback
from datetime import datetime, timezone
from typing import Iterable

_URL_SENSIVEL = re.compile(
    r"https?://([A-Za-z0-9.-]*(?:logic\.azure\.com|powerplatform\.com|hc-ping\.com))[^\s\"'<>]*",
    re.IGNORECASE,
)

_PADRAO_LOGRECORD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class RedactingFilter(logging.Filter):
    """Troca segredos literais e URLs de Teams/heartbeat por <redacted:host>."""

    def __init__(self, segredos: Iterable[str] = ()):
        super().__init__()
        self._segredos = [s for s in segredos if s]

    def redigir(self, texto: str) -> str:
        for segredo in self._segredos:
            if segredo in texto:
                texto = texto.replace(segredo, "<redacted>")
        return _URL_SENSIVEL.sub(lambda m: f"<redacted:{m.group(1)}>", texto)

    def _redigir_valor(self, valor):
        if isinstance(valor, str):
            return self.redigir(valor)
        if isinstance(valor, dict):
            return {k: self._redigir_valor(v) for k, v in valor.items()}
        if isinstance(valor, (list, tuple)):
            return [self._redigir_valor(v) for v in valor]
        return valor

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redigir(record.getMessage())
        record.args = ()
        if record.exc_info:
            texto = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = self.redigir(texto)
            record.exc_info = None
        for chave in set(record.__dict__) - _PADRAO_LOGRECORD:
            record.__dict__[chave] = self._redigir_valor(record.__dict__[chave])
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        linha = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": getattr(record, "event", record.name),
            "msg": record.getMessage(),
        }
        for chave, valor in record.__dict__.items():
            if chave not in _PADRAO_LOGRECORD and chave != "event":
                linha[chave] = valor
        if record.exc_info:
            linha["exc"] = "".join(traceback.format_exception(*record.exc_info))
        elif record.exc_text:
            linha["exc"] = record.exc_text
        return json.dumps(linha, ensure_ascii=False, default=str)


def configurar_logging(nivel: str, segredos: Iterable[str] = (), stream=None) -> logging.Logger:
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter(segredos))
    raiz = logging.getLogger("cato_monitor")
    raiz.handlers = [handler]
    raiz.setLevel(nivel)
    raiz.propagate = False
    return raiz


def evento(log: logging.Logger, nivel: int, nome: str, msg: str = "", **extras) -> None:
    """Atalho: log estruturado com `event` e campos extras."""
    log.log(nivel, msg or nome, extra={"event": nome, **extras})
