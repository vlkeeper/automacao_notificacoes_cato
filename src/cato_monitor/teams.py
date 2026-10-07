"""Entrega dos cards ao Teams (Workflows): fila global ordenada, para na primeira falha."""

from __future__ import annotations

import logging
import time
from typing import Callable

import requests

from .cards import renderizar
from .config import Config
from .logs import evento
from .modelos import EstadoMonitor

log = logging.getLogger("cato_monitor.teams")

TIMEOUT = (5, 10)
MAX_ENVIOS_POR_CICLO = 20
ESPACO_ENTRE_ENVIOS = 1.0
MAX_TENTATIVAS_HTTP = 2
BACKOFF_BASE = 2.0
BACKOFF_TETO = 30.0


def _mensagem(card: dict) -> dict:
    return {
        "type": "message",
        "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}
        ],
    }


def _retry_after(resp: requests.Response) -> float | None:
    try:
        return float(resp.headers["Retry-After"])
    except (KeyError, ValueError):
        return None


def _enviar(sessao: requests.Session, cfg: Config, corpo: dict, dormir) -> tuple[bool, str]:
    """Faz o POST (com até 2 tentativas em 429/5xx). Devolve (entregue, status_sanitizado)."""
    status = "conexao"
    for tentativa in range(1, MAX_TENTATIVAS_HTTP + 1):
        try:
            resp = sessao.post(cfg.teams_webhook_url, json=corpo, timeout=TIMEOUT)
        except requests.Timeout:
            return False, "timeout"
        except requests.RequestException:
            return False, "conexao"
        if 200 <= resp.status_code < 300:
            return True, str(resp.status_code)
        status = f"http_{resp.status_code}"
        if (resp.status_code == 429 or resp.status_code >= 500) and tentativa < MAX_TENTATIVAS_HTTP:
            espera = _retry_after(resp)
            dormir(min(espera if espera is not None else BACKOFF_BASE, BACKOFF_TETO))
            continue
        break
    return False, status


def drenar(
    estado: EstadoMonitor,
    cfg: Config,
    salvar: Callable[[], None],
    sessao: requests.Session | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> int:
    """Envia a fila em ordem. Devolve quantos eventos foram entregues neste ciclo."""
    sessao = sessao or requests.Session()
    enviados = 0
    while estado.pendente_envio and enviados < MAX_ENVIOS_POR_CICLO:
        ev = estado.pendente_envio[0]
        corpo = _mensagem(renderizar(ev, cfg.tz))
        entregue, status = _enviar(sessao, cfg, corpo, dormir)
        if entregue:
            estado.pendente_envio.pop(0)
            salvar()
            enviados += 1
            evento(log, logging.INFO, "envio_teams", id=ev.id, tipo=ev.tipo.value, status=status,
                   tentativas=ev.tentativas + 1)
            if estado.pendente_envio and enviados < MAX_ENVIOS_POR_CICLO:
                dormir(ESPACO_ENTRE_ENVIOS)
        else:
            ev.tentativas += 1
            ev.ultimo_erro = status  # sanitizado: status/tipo de erro, nunca a URL
            salvar()
            evento(log, logging.WARNING, "envio_teams", id=ev.id, tipo=ev.tipo.value, status=status,
                   tentativas=ev.tentativas)
            break  # head-of-line: preserva a ordem
    return enviados
