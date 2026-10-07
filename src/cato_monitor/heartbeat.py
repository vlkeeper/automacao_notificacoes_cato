"""Heartbeat externo (Healthchecks.io ou compatível). Falha só é logada; nunca interrompe o laço."""

from __future__ import annotations

import logging

import requests

from .config import Config
from .logs import evento

log = logging.getLogger("cato_monitor.heartbeat")

TIMEOUT = 10


def ping(cfg: Config, ok: bool, sessao: requests.Session | None = None) -> bool:
    rota = "ok" if ok else "fail"
    url = cfg.heartbeat_url if ok else cfg.heartbeat_url.rstrip("/") + "/fail"
    try:
        resp = (sessao or requests).get(url, timeout=TIMEOUT)
    except requests.RequestException as exc:
        evento(log, logging.WARNING, "heartbeat", rota=rota, status=type(exc).__name__)
        return False
    if not resp.ok:
        evento(log, logging.WARNING, "heartbeat", rota=rota, status=resp.status_code)
        return False
    evento(log, logging.DEBUG, "heartbeat", rota=rota, status=resp.status_code)
    return True
