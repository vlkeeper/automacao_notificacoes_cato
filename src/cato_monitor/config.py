"""Configuração por variáveis de ambiente, validada inteira na inicialização.

Todos os erros são acumulados e reportados numa única mensagem (exit 1).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

URL_CATO_PADRAO = "https://api.catonetworks.com/api/v1/graphql2"
NIVEIS_LOG = ("DEBUG", "INFO", "WARNING", "ERROR")


class ConfigInvalida(Exception):
    def __init__(self, erros: list[str]):
        super().__init__("; ".join(erros))
        self.erros = erros


@dataclass(frozen=True)
class Config:
    cato_api_key: str
    cato_account_id: str
    cato_api_url: str
    teams_webhook_url: str
    heartbeat_url: str
    intervalo_segundos: int
    tolerancia_segundos: int
    lembrete_horario: time
    tz: ZoneInfo
    tz_nome: str
    state_dir: Path
    log_level: str

    def segredos(self) -> list[str]:
        """Valores literais que nunca podem aparecer em logs."""
        return [self.cato_api_key, self.teams_webhook_url, self.heartbeat_url]

    def exibicao(self) -> dict[str, object]:
        """Configuração efetiva com os segredos mascarados."""
        return {
            "CATO_API_KEY": "****" + self.cato_api_key[-4:],
            "CATO_ACCOUNT_ID": self.cato_account_id,
            "CATO_API_URL": self.cato_api_url,
            "TEAMS_WEBHOOK_URL": _host(self.teams_webhook_url),
            "HEARTBEAT_URL": _host(self.heartbeat_url),
            "INTERVALO_SEGUNDOS": self.intervalo_segundos,
            "TOLERANCIA_SEGUNDOS": self.tolerancia_segundos,
            "LEMBRETE_HORARIO": self.lembrete_horario.strftime("%H:%M"),
            "TZ": self.tz_nome,
            "STATE_DIR": str(self.state_dir),
            "LOG_LEVEL": self.log_level,
        }


def _host(url: str) -> str:
    return urlparse(url).hostname or "?"


def _url_https(valor: str) -> bool:
    p = urlparse(valor)
    return p.scheme == "https" and bool(p.hostname)


def _inteiro(env: Mapping[str, str], nome: str, padrao: int, minimo: int, maximo: int | None,
             erros: list[str]) -> int | None:
    bruto = env.get(nome, "").strip()
    if not bruto:
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        erros.append(f"{nome}={bruto!r} não é um inteiro")
        return None
    if valor < minimo:
        erros.append(f"{nome}={valor} abaixo do mínimo {minimo}")
        return None
    if maximo is not None and valor > maximo:
        erros.append(f"{nome}={valor} acima do máximo {maximo}")
        return None
    return valor


def _gravavel(pasta: Path) -> bool:
    return pasta.is_dir() and os.access(pasta, os.W_OK | os.X_OK)


def ler_config(env: Mapping[str, str] | None = None) -> Config:
    """Valida o ambiente e devolve a Config; levanta ConfigInvalida com TODOS os erros."""
    env = os.environ if env is None else env
    erros: list[str] = []

    api_key = env.get("CATO_API_KEY", "").strip()
    if not api_key:
        erros.append("CATO_API_KEY ausente")
    elif re.search(r"\s", api_key):
        erros.append("CATO_API_KEY não pode conter espaços")

    account_id = env.get("CATO_ACCOUNT_ID", "").strip()
    if not account_id:
        erros.append("CATO_ACCOUNT_ID ausente")
    elif not account_id.isdigit():
        erros.append("CATO_ACCOUNT_ID deve conter somente dígitos")

    api_url = env.get("CATO_API_URL", "").strip() or URL_CATO_PADRAO
    if not _url_https(api_url):
        erros.append("CATO_API_URL deve ser uma URL https://")

    urls: dict[str, str] = {}
    for nome in ("TEAMS_WEBHOOK_URL", "HEARTBEAT_URL"):
        valor = env.get(nome, "").strip()
        if not valor:
            erros.append(f"{nome} ausente")
        elif not _url_https(valor):
            erros.append(f"{nome} deve ser uma URL https://")
        urls[nome] = valor

    intervalo = _inteiro(env, "INTERVALO_SEGUNDOS", 60, 30, 120, erros)
    tolerancia = _inteiro(env, "TOLERANCIA_SEGUNDOS", 180, 60, 3600, erros)
    if intervalo is not None and tolerancia is not None and tolerancia < intervalo:
        erros.append(
            f"TOLERANCIA_SEGUNDOS={tolerancia} deve ser maior ou igual a INTERVALO_SEGUNDOS={intervalo}"
        )

    horario_txt = env.get("LEMBRETE_HORARIO", "").strip() or "08:00"
    horario = None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", horario_txt)
    if m and int(m.group(1)) <= 23 and int(m.group(2)) <= 59:
        horario = time(int(m.group(1)), int(m.group(2)))
    else:
        erros.append(f"LEMBRETE_HORARIO={horario_txt!r} inválido (use HH:MM, 24 h)")

    tz_nome = env.get("TZ", "").strip() or "America/Sao_Paulo"
    tz = None
    try:
        tz = ZoneInfo(tz_nome)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        erros.append(f"TZ={tz_nome!r} não é um fuso válido")

    state_dir = Path(env.get("STATE_DIR", "").strip() or "/data")
    if not _gravavel(state_dir):
        erros.append(f"STATE_DIR={str(state_dir)!r} não existe ou não é gravável")

    nivel = (env.get("LOG_LEVEL", "").strip() or "INFO").upper()
    if nivel not in NIVEIS_LOG:
        erros.append(f"LOG_LEVEL={nivel!r} inválido (use {'/'.join(NIVEIS_LOG)})")

    if erros:
        raise ConfigInvalida(erros)

    return Config(
        cato_api_key=api_key,
        cato_account_id=account_id,
        cato_api_url=api_url,
        teams_webhook_url=urls["TEAMS_WEBHOOK_URL"],
        heartbeat_url=urls["HEARTBEAT_URL"],
        intervalo_segundos=intervalo,
        tolerancia_segundos=tolerancia,
        lembrete_horario=horario,
        tz=tz,
        tz_nome=tz_nome,
        state_dir=state_dir,
        log_level=nivel,
    )


def carregar_config(env: Mapping[str, str] | None = None) -> Config:
    """Como `ler_config`, mas em caso de erro loga `config_invalida` em stderr e sai com 1."""
    try:
        return ler_config(env)
    except ConfigInvalida as exc:
        linha = {"level": "ERROR", "event": "config_invalida", "erros": exc.erros}
        print(json.dumps(linha, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
