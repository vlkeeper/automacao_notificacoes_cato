"""Cliente da API GraphQL da Cato (somente leitura). Nunca levanta exceção para o laço."""

from __future__ import annotations

import logging
import random
import time
from typing import Callable

import requests

from .config import Config
from .logs import evento
from .modelos import ConsultaFalhou, ConsultaOk, ResultadoConsulta
from .snapshot import normalizar

log = logging.getLogger("cato_monitor.cato")

TIMEOUT = (5, 20)
BACKOFF_BASE = 2.0
BACKOFF_TETO = 30.0
MAX_TENTATIVAS = 3

# Somente leitura (FR-013): uma única query, sem mutation.
QUERY = """
query MonitorSnapshot($accountID: ID!) {
  accountSnapshot(accountID: $accountID) {
    id
    timestamp
    sites {
      id
      connectivityStatus
      operationalStatus
      lastConnected
      info { name isHA interfaces { id destType wanRole } }
      devices {
        id
        haRole
        connected
        socketInfo { id serial isPrimary }
        interfaces { id name connected tunnelUptime }
        interfacesLinkState { id up }
      }
    }
  }
}
""".strip()


def _retry_after(resp: requests.Response) -> float | None:
    bruto = resp.headers.get("Retry-After")
    try:
        return float(bruto) if bruto is not None else None
    except ValueError:
        return None


class CatoClient:
    def __init__(
        self,
        cfg: Config,
        sessao: requests.Session | None = None,
        dormir: Callable[[float], None] = time.sleep,
        monotonico: Callable[[], float] = time.monotonic,
    ):
        self._cfg = cfg
        self._sessao = sessao or requests.Session()
        self._dormir = dormir
        self._monotonico = monotonico

    def consultar(self, estado_tem_sites: bool = False) -> ResultadoConsulta:
        inicio = self._monotonico()
        orcamento = min(60.0, float(self._cfg.intervalo_segundos))
        try:
            resultado, tentativas = self._consultar(estado_tem_sites, inicio, orcamento)
        except Exception as exc:  # rede de segurança: a consulta nunca derruba o laço
            resultado, tentativas = ConsultaFalhou(f"erro_inesperado:{type(exc).__name__}"), 0
        evento(
            log,
            logging.INFO if isinstance(resultado, ConsultaOk) else logging.WARNING,
            "consulta_cato",
            resultado="ok" if isinstance(resultado, ConsultaOk) else "falhou",
            motivo=None if isinstance(resultado, ConsultaOk) else resultado.motivo,
            tentativas=tentativas,
            duracao_ms=int((self._monotonico() - inicio) * 1000),
        )
        return resultado

    def _consultar(self, estado_tem_sites: bool, inicio: float, orcamento: float):
        ultimo = ConsultaFalhou("conexao")
        for tentativa in range(1, MAX_TENTATIVAS + 1):
            resposta, falha = self._requisitar()
            if falha is None:
                return self._classificar(resposta, estado_tem_sites), tentativa
            ultimo, retentavel, retry_after = falha
            if not retentavel:  # 4xx ≠ 429
                return ultimo, tentativa
            if tentativa == MAX_TENTATIVAS:
                break
            espera = retry_after if retry_after is not None else self._backoff(tentativa)
            espera = min(espera, BACKOFF_TETO)
            if self._monotonico() - inicio + espera > orcamento:
                break
            self._dormir(espera)
        return ultimo, tentativa

    def _requisitar(self):
        """Devolve (resposta, None) ou (None, (ConsultaFalhou, retentavel, retry_after))."""
        try:
            resp = self._sessao.post(
                self._cfg.cato_api_url,
                json={"query": QUERY, "variables": {"accountID": self._cfg.cato_account_id}},
                headers={"x-api-key": self._cfg.cato_api_key, "Accept": "application/json",
                         "Content-Type": "application/json"},
                timeout=TIMEOUT,
            )
        except requests.Timeout:
            return None, (ConsultaFalhou("timeout"), True, None)
        except requests.RequestException:
            return None, (ConsultaFalhou("conexao"), True, None)

        status = resp.status_code
        if status == 429 or status >= 500:
            return None, (ConsultaFalhou(f"http_{status}"), True, _retry_after(resp))
        if status >= 400:
            if status in (401, 403):
                evento(log, logging.ERROR, "cato_nao_autorizado",
                       f"HTTP {status}: verifique CATO_API_KEY/permissões")
            return None, (ConsultaFalhou(f"http_{status}"), False, None)
        return resp, None

    def _backoff(self, tentativa: int) -> float:
        """Exponencial (base 2 s, fator 2) com jitter de até 25 %."""
        return BACKOFF_BASE * (2 ** (tentativa - 1)) * (1 + random.random() * 0.25)

    def _classificar(self, resp: requests.Response, estado_tem_sites: bool) -> ResultadoConsulta:
        try:
            corpo = resp.json()
        except ValueError:
            return ConsultaFalhou("json_invalido")
        if not isinstance(corpo, dict):
            return ConsultaFalhou("schema_invalido")
        if corpo.get("errors"):
            return ConsultaFalhou("graphql_errors")
        resultado = normalizar(corpo, permitir_vazio=not estado_tem_sites)
        if isinstance(resultado, ConsultaFalhou):
            return resultado
        return ConsultaOk(snapshot=resultado)
