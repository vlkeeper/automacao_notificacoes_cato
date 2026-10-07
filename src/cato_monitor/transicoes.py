"""Tabela de transições de UM item (site ou link). Função pura: sem I/O nem relógio global."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import TypeVar

from .modelos import EstadoItem, Link, Site

Item = TypeVar("Item", Site, Link)


class TipoAcao(str, Enum):
    QUEDA = "QUEDA"
    RETORNO = "RETORNO"


@dataclass(frozen=True)
class Acao:
    tipo: TipoAcao
    duracao: timedelta | None = None  # só no RETORNO


def _limpar(item: Item) -> Item:
    novo = replace(item, estado=EstadoItem.ONLINE, inicio_queda=None, notificado=False)
    if isinstance(novo, Link):
        novo = replace(novo, coberto_pelo_site=False)
    return novo


def proximo_estado(
    item: Item, obs_offline: bool | None, agora: datetime, tolerancia: timedelta
) -> tuple[Item, list[Acao]]:
    """Aplica uma observação ao item (data-model §3.1).

    `obs_offline=None` (consulta falha ou item ausente) deixa o item inalterado.
    """
    if obs_offline is None:
        return item, []

    estado = item.estado
    if estado == EstadoItem.ONLINE:
        if obs_offline:
            return replace(item, estado=EstadoItem.PENDENTE_OFFLINE, inicio_queda=agora), []
        return item, []

    if estado == EstadoItem.PENDENTE_OFFLINE:
        if not obs_offline:
            return _limpar(item), []
        if agora - item.inicio_queda >= tolerancia:
            return (
                replace(item, estado=EstadoItem.OFFLINE_NOTIFICADO, notificado=True),
                [Acao(TipoAcao.QUEDA)],
            )
        return item, []

    # OFFLINE_NOTIFICADO
    if obs_offline:
        return item, []
    duracao = agora - item.inicio_queda
    return _limpar(item), [Acao(TipoAcao.RETORNO, duracao)]
