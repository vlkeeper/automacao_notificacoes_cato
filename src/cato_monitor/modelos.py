"""Entidades do monitor (ver specs/001-cato-socket/data-model.md).

Todo timestamp é datetime aware em UTC; na persistência vira ISO 8601 com +00:00.
Os nomes de sites e links são guardados exatamente como vêm da Cato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

LIMITE_FALHAS = 5
LIMITE_AUSENCIAS = 3
SCHEMA_VERSION = 1
# Pendências por card do lembrete, para que cada card fique abaixo de ~24 KB (R-007).
MAX_PENDENCIAS_POR_CARD = 40
ORCAMENTO_BYTES_LEMBRETE = 18_000  # folga sobre o limite de 24 KB por card
BYTES_POR_LINHA = 560  # custo fixo estimado de uma linha da tabela, fora os nomes


class EstadoItem(str, Enum):
    ONLINE = "ONLINE"
    PENDENTE_OFFLINE = "PENDENTE_OFFLINE"
    OFFLINE_NOTIFICADO = "OFFLINE_NOTIFICADO"


class Origem(str, Enum):
    OBSERVADO = "observado"
    LINHA_BASE = "linha_base"


class TipoEvento(str, Enum):
    LINK_OFFLINE = "LINK_OFFLINE"
    SITE_OFFLINE = "SITE_OFFLINE"
    LINK_RETORNO = "LINK_RETORNO"
    SITE_RETORNO = "SITE_RETORNO"
    LEMBRETE_DIARIO = "LEMBRETE_DIARIO"
    MONITOR_FALHA = "MONITOR_FALHA"
    MONITOR_RECUPERADO = "MONITOR_RECUPERADO"
    MONITOR_INICIADO = "MONITOR_INICIADO"


def ts_para_str(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        raise ValueError("timestamp sem fuso horário")
    return ts.astimezone(timezone.utc).isoformat(timespec="seconds")


def str_para_ts(valor: str | None) -> datetime | None:
    if valor is None:
        return None
    ts = datetime.fromisoformat(valor)
    if ts.tzinfo is None:
        raise ValueError("timestamp sem fuso horário")
    return ts.astimezone(timezone.utc)


# --------------------------------------------------------------------------- persistidas


@dataclass
class Link:
    nome: str
    tipo: str  # "WAN" | "LAN"
    socket: str = ""
    estado: EstadoItem = EstadoItem.ONLINE
    inicio_queda: datetime | None = None
    notificado: bool = False
    coberto_pelo_site: bool = False
    origem: Origem = Origem.OBSERVADO
    ausencias: int = 0

    def para_dict(self) -> dict[str, Any]:
        return {
            "nome": self.nome,
            "tipo": self.tipo,
            "socket": self.socket,
            "estado": self.estado.value,
            "inicio_queda": ts_para_str(self.inicio_queda),
            "notificado": self.notificado,
            "coberto_pelo_site": self.coberto_pelo_site,
            "origem": self.origem.value,
            "ausencias": self.ausencias,
        }

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "Link":
        return cls(
            nome=d["nome"],
            tipo=d["tipo"],
            socket=d["socket"],
            estado=EstadoItem(d["estado"]),
            inicio_queda=str_para_ts(d["inicio_queda"]),
            notificado=d["notificado"],
            coberto_pelo_site=d["coberto_pelo_site"],
            origem=Origem(d["origem"]),
            ausencias=d["ausencias"],
        )


@dataclass
class Site:
    nome: str
    estado: EstadoItem = EstadoItem.ONLINE
    inicio_queda: datetime | None = None
    notificado: bool = False
    origem: Origem = Origem.OBSERVADO
    ausencias: int = 0
    links: dict[str, Link] = field(default_factory=dict)

    def para_dict(self) -> dict[str, Any]:
        return {
            "nome": self.nome,
            "estado": self.estado.value,
            "inicio_queda": ts_para_str(self.inicio_queda),
            "notificado": self.notificado,
            "origem": self.origem.value,
            "ausencias": self.ausencias,
            "links": {k: v.para_dict() for k, v in self.links.items()},
        }

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "Site":
        return cls(
            nome=d["nome"],
            estado=EstadoItem(d["estado"]),
            inicio_queda=str_para_ts(d["inicio_queda"]),
            notificado=d["notificado"],
            origem=Origem(d["origem"]),
            ausencias=d["ausencias"],
            links={k: Link.de_dict(v) for k, v in d["links"].items()},
        )


@dataclass
class SituacaoMonitor:
    falhas_consecutivas: int = 0
    alerta_falha_enviado: bool = False
    ultimo_ciclo_concluido_em: datetime | None = None
    ultima_consulta_ok_em: datetime | None = None
    ultimo_lembrete_data: str | None = None
    proximo_seq: int = 1

    def para_dict(self) -> dict[str, Any]:
        return {
            "falhas_consecutivas": self.falhas_consecutivas,
            "alerta_falha_enviado": self.alerta_falha_enviado,
            "ultimo_ciclo_concluido_em": ts_para_str(self.ultimo_ciclo_concluido_em),
            "ultima_consulta_ok_em": ts_para_str(self.ultima_consulta_ok_em),
            "ultimo_lembrete_data": self.ultimo_lembrete_data,
            "proximo_seq": self.proximo_seq,
        }

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "SituacaoMonitor":
        return cls(
            falhas_consecutivas=d["falhas_consecutivas"],
            alerta_falha_enviado=d["alerta_falha_enviado"],
            ultimo_ciclo_concluido_em=str_para_ts(d["ultimo_ciclo_concluido_em"]),
            ultima_consulta_ok_em=str_para_ts(d["ultima_consulta_ok_em"]),
            ultimo_lembrete_data=d["ultimo_lembrete_data"],
            proximo_seq=d["proximo_seq"],
        )


@dataclass
class EventoNotificacao:
    id: str
    tipo: TipoEvento
    ocorrido_em: datetime
    criado_em: datetime
    dados: dict[str, Any]
    tentativas: int = 0
    ultimo_erro: str | None = None

    def para_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tipo": self.tipo.value,
            "ocorrido_em": ts_para_str(self.ocorrido_em),
            "criado_em": ts_para_str(self.criado_em),
            "tentativas": self.tentativas,
            "ultimo_erro": self.ultimo_erro,
            "dados": self.dados,
        }

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "EventoNotificacao":
        return cls(
            id=d["id"],
            tipo=TipoEvento(d["tipo"]),
            ocorrido_em=str_para_ts(d["ocorrido_em"]),
            criado_em=str_para_ts(d["criado_em"]),
            tentativas=d["tentativas"],
            ultimo_erro=d["ultimo_erro"],
            dados=d["dados"],
        )


@dataclass
class EstadoMonitor:
    monitor: SituacaoMonitor = field(default_factory=SituacaoMonitor)
    sites: dict[str, Site] = field(default_factory=dict)
    pendente_envio: list[EventoNotificacao] = field(default_factory=list)
    atualizado_em: datetime | None = None

    def para_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "atualizado_em": ts_para_str(self.atualizado_em),
            "monitor": self.monitor.para_dict(),
            "sites": {k: v.para_dict() for k, v in self.sites.items()},
            "pendente_envio": [e.para_dict() for e in self.pendente_envio],
        }

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "EstadoMonitor":
        return cls(
            atualizado_em=str_para_ts(d["atualizado_em"]),
            monitor=SituacaoMonitor.de_dict(d["monitor"]),
            sites={k: Site.de_dict(v) for k, v in d["sites"].items()},
            pendente_envio=[EventoNotificacao.de_dict(e) for e in d["pendente_envio"]],
        )


def verificar_invariantes(estado: EstadoMonitor) -> list[str]:
    """Devolve a lista de violações das invariantes do data-model (vazia = íntegro)."""
    erros: list[str] = []

    def checar(rotulo: str, item: Site | Link) -> None:
        if item.estado == EstadoItem.ONLINE:
            if item.inicio_queda is not None or item.notificado:
                erros.append(f"{rotulo}: ONLINE com inicio_queda/notificado")
            if isinstance(item, Link) and item.coberto_pelo_site:
                erros.append(f"{rotulo}: ONLINE com coberto_pelo_site")
        else:
            if item.inicio_queda is None:
                erros.append(f"{rotulo}: fora de ONLINE sem inicio_queda")
        if item.estado == EstadoItem.OFFLINE_NOTIFICADO and not item.notificado:
            erros.append(f"{rotulo}: OFFLINE_NOTIFICADO sem notificado")

    for sid, site in estado.sites.items():
        checar(f"site {sid}", site)
        for lid, link in site.links.items():
            checar(f"link {sid}/{lid}", link)
    return erros


# --------------------------------------------------------------------------- transitórias


@dataclass(frozen=True)
class ObservacaoLink:
    nome: str
    tipo: str
    socket: str
    online: bool


@dataclass(frozen=True)
class ObservacaoSite:
    nome: str
    conectado: bool
    links: dict[str, ObservacaoLink] = field(default_factory=dict)


@dataclass(frozen=True)
class Snapshot:
    sites: dict[str, ObservacaoSite] = field(default_factory=dict)


@dataclass(frozen=True)
class ConsultaOk:
    snapshot: Snapshot
    recebido_em: datetime | None = None


@dataclass(frozen=True)
class ConsultaFalhou:
    motivo: str


ResultadoConsulta = ConsultaOk | ConsultaFalhou
