"""Canais do Teams: roteamento tipo -> canal e avaliação da entrega. Puro: sem I/O nem relógio global."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from .modelos import (
    CANAL_OPERACIONAL,
    CANAL_REDE,
    EstadoMonitor,
    EventoNotificacao,
    TipoEvento,
    ts_para_str,
)

LIMITE_SEM_ENTREGA_S = 900  # 15 min de falha contínua antes do aviso no outro canal


class Canal(str, Enum):
    REDE = CANAL_REDE
    OPERACIONAL = CANAL_OPERACIONAL

    @property
    def outro(self) -> "Canal":
        return Canal.OPERACIONAL if self is Canal.REDE else Canal.REDE


# Sem valor padrão: tipo novo sem mapeamento levanta KeyError (FR-004). Os tipos da feature 002
# (falha/normalização de gravação no banco) entram aqui como OPERACIONAL quando forem criados.
MAPA_CANAL: dict[TipoEvento, Canal] = {
    TipoEvento.LINK_OFFLINE: Canal.REDE,
    TipoEvento.SITE_OFFLINE: Canal.REDE,
    TipoEvento.LINK_RETORNO: Canal.REDE,
    TipoEvento.SITE_RETORNO: Canal.REDE,
    TipoEvento.LEMBRETE_DIARIO: Canal.REDE,
    TipoEvento.MONITOR_FALHA: Canal.OPERACIONAL,
    TipoEvento.MONITOR_RECUPERADO: Canal.OPERACIONAL,
    TipoEvento.MONITOR_INICIADO: Canal.OPERACIONAL,
}


def canal_do_evento(ev: EventoNotificacao) -> Canal:
    if ev.tipo in (TipoEvento.CANAL_SEM_ENTREGA, TipoEvento.CANAL_NORMALIZADO):
        return Canal(ev.dados["canal_afetado"]).outro
    return MAPA_CANAL[ev.tipo]


def avaliar_entrega(
    estado: EstadoMonitor,
    resultados: dict[Canal, tuple[int, bool]],
    agora: datetime,
    limite_s: int = LIMITE_SEM_ENTREGA_S,
) -> list[EventoNotificacao]:
    """Atualiza `estado.entrega` e devolve os avisos de sem entrega/normalização.

    `resultados[canal] = (enviados, falhou)` da drenagem do ciclo. Os eventos devolvidos se destinam
    ao OUTRO canal; quem chama os anexa à fila (o `proximo_seq` é consumido aqui).
    """
    novos: list[EventoNotificacao] = []

    def criar(tipo: TipoEvento, dados: dict) -> EventoNotificacao:
        seq = estado.monitor.proximo_seq
        estado.monitor.proximo_seq += 1
        return EventoNotificacao(id=f"evt-{seq:06d}", tipo=tipo, ocorrido_em=agora,
                                 criado_em=agora, dados=dados)

    for canal in Canal:
        enviados, falhou = resultados.get(canal, (0, False))
        sit = estado.entrega[canal.value]
        if enviados > 0:  # entregou algo: o canal está funcionando
            if sit.aviso_emitido and sit.falha_desde is not None:
                novos.append(criar(TipoEvento.CANAL_NORMALIZADO, {
                    "canal_afetado": canal.value,
                    "desde": ts_para_str(sit.falha_desde),
                    "duracao_s": int((agora - sit.falha_desde).total_seconds()),
                }))
            sit.falha_desde = None
            sit.aviso_emitido = False
        elif falhou:
            if sit.falha_desde is None:
                sit.falha_desde = agora
            if not sit.aviso_emitido and (agora - sit.falha_desde).total_seconds() >= limite_s:
                novos.append(criar(TipoEvento.CANAL_SEM_ENTREGA, {
                    "canal_afetado": canal.value,
                    "desde": ts_para_str(sit.falha_desde),
                    "pendentes": len(estado.filas[canal.value]),
                }))
                sit.aviso_emitido = True
    return novos
