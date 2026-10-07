"""Laço principal: consulta → motor → fila → envio → heartbeat."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import requests

from . import estado_store as store
from . import heartbeat, teams
from .cato_client import CatoClient
from .config import Config
from .logs import evento
from .modelos import LIMITE_FALHAS, ConsultaOk, EstadoMonitor
from .motor import avaliar_ciclo_detalhado
from .relogio import Relogio, RelogioSistema

log = logging.getLogger("cato_monitor.daemon")


class Daemon:
    def __init__(
        self,
        cfg: Config,
        estado: EstadoMonitor,
        cliente: CatoClient,
        relogio: Relogio | None = None,
        sessao_teams: requests.Session | None = None,
        sessao_heartbeat: requests.Session | None = None,
        dormir: Callable[[float], None] = time.sleep,
        monotonico: Callable[[], float] = time.monotonic,
    ):
        self.cfg = cfg
        self.estado = estado
        self.cliente = cliente
        self.relogio = relogio or RelogioSistema()
        self._sessao_teams = sessao_teams
        self._sessao_hb = sessao_heartbeat
        self._dormir_envio = dormir
        self._monotonico = monotonico
        self._parar = threading.Event()

    def parar(self) -> None:
        self._parar.set()

    def _salvar(self) -> None:
        store.salvar(self.estado, self.cfg.state_dir, self.relogio.agora())

    def executar_ciclo(self) -> None:
        inicio = self._monotonico()
        agora = self.relogio.agora()

        resultado = self.cliente.consultar(estado_tem_sites=bool(self.estado.sites))
        novo, eventos, det = avaliar_ciclo_detalhado(self.estado, resultado, agora, self.cfg)
        self.estado = novo

        for t in det.transicoes:
            evento(log, logging.INFO, "transicao", **t)
        for r in det.registros:
            evento(log, logging.INFO, r["event"], site_id=r["site_id"], link_id=r["link_id"])
        for e in eventos:
            evento(log, logging.INFO, "evento_enfileirado", id=e.id, tipo=e.tipo.value)

        # Persiste ANTES de enviar: um evento gerado nunca se perde se o processo cair.
        self.estado.pendente_envio.extend(eventos)
        self._salvar()

        enviados = teams.drenar(
            self.estado, self.cfg, self._salvar, self._sessao_teams, self._dormir_envio
        )

        concluido = self.relogio.agora()
        self.estado.monitor.ultimo_ciclo_concluido_em = concluido
        self._salvar()
        store.gravar_last_cycle(self.cfg.state_dir, concluido)

        falhas = self.estado.monitor.falhas_consecutivas
        heartbeat.ping(self.cfg, ok=falhas < LIMITE_FALHAS, sessao=self._sessao_hb)

        evento(
            log, logging.INFO, "ciclo_concluido",
            duracao_ms=int((self._monotonico() - inicio) * 1000),
            sites=len(self.estado.sites),
            links=sum(len(s.links) for s in self.estado.sites.values()),
            consulta="ok" if isinstance(resultado, ConsultaOk) else "falhou",
            transicoes=len(det.transicoes),
            eventos_gerados=len(eventos),
            fila_pendente=len(self.estado.pendente_envio),
            enviados=enviados,
            falhas_consecutivas=falhas,
        )

    def run(self) -> None:
        while not self._parar.is_set():
            inicio = self._monotonico()
            try:
                self.executar_ciclo()
            except Exception:  # nenhuma falha de um ciclo encerra o monitor
                log.exception("ciclo falhou", extra={"event": "ciclo_erro"})
            restante = self.cfg.intervalo_segundos - (self._monotonico() - inicio)
            if restante > 0:
                self._parar.wait(restante)
        self._salvar()
