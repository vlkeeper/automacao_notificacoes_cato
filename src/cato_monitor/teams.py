"""Entrega dos cards ao Teams (Workflows): uma fila por canal, ordenada, para na primeira falha."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import requests

from .canais import Canal
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


def _enviar(sessao: requests.Session, url: str, corpo: dict, dormir) -> tuple[bool, str]:
    """Faz o POST (com até 2 tentativas em 429/5xx). Devolve (entregue, status_sanitizado)."""
    status = "conexao"
    for tentativa in range(1, MAX_TENTATIVAS_HTTP + 1):
        try:
            resp = sessao.post(url, json=corpo, timeout=TIMEOUT)
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


def url_do_canal(cfg: Config, canal: Canal) -> str:
    return cfg.teams_webhook_url if canal is Canal.REDE else cfg.teams_webhook_operacional_url


def drenar_canal(
    estado: EstadoMonitor,
    canal: Canal,
    cfg: Config,
    salvar: Callable[[], None],
    sessao: requests.Session | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> tuple[int, bool]:
    """Envia a fila do canal em ordem. Devolve (entregues neste ciclo, falhou)."""
    sessao = sessao or requests.Session()
    fila = estado.filas[canal.value]
    url = url_do_canal(cfg, canal)
    enviados = 0
    while fila and enviados < MAX_ENVIOS_POR_CICLO:
        ev = fila[0]
        corpo = _mensagem(renderizar(ev, cfg.tz))
        entregue, status = _enviar(sessao, url, corpo, dormir)
        if entregue:
            fila.pop(0)
            salvar()
            enviados += 1
            evento(log, logging.INFO, "envio_teams", canal=canal.value, id=ev.id, tipo=ev.tipo.value,
                   status=status, tentativas=ev.tentativas + 1)
            if fila and enviados < MAX_ENVIOS_POR_CICLO:
                dormir(ESPACO_ENTRE_ENVIOS)
        else:
            ev.tentativas += 1
            ev.ultimo_erro = status  # sanitizado: status/tipo de erro, nunca a URL
            salvar()
            evento(log, logging.WARNING, "envio_teams", canal=canal.value, id=ev.id, tipo=ev.tipo.value,
                   status=status, tentativas=ev.tentativas)
            return enviados, True  # head-of-line: preserva a ordem
    return enviados, False


def drenar_todos(
    estado: EstadoMonitor,
    cfg: Config,
    salvar: Callable[[], None],
    sessao: requests.Session | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> dict[Canal, tuple[int, bool]]:
    """Drena os dois canais em paralelo (uma thread por canal): um não atrasa o outro."""
    trava = threading.Lock()
    resultados: dict[Canal, tuple[int, bool]] = {}

    def salvar_seguro() -> None:
        with trava:
            salvar()

    def trabalho(canal: Canal) -> None:
        try:
            resultados[canal] = drenar_canal(estado, canal, cfg, salvar_seguro, sessao, dormir)
        except Exception:  # um canal com defeito não pode derrubar o outro
            log.exception("drenagem falhou",
                          extra={"event": "envio_teams_erro", "canal": canal.value})
            resultados[canal] = (0, True)

    threads = [threading.Thread(target=trabalho, args=(c,), name=f"teams-{c.value}") for c in Canal]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return resultados
