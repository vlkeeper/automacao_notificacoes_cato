"""Construtores de observações e estados para os testes do motor."""

from cato_monitor.canais import canal_do_evento
from cato_monitor.modelos import (
    ConsultaOk,
    EstadoItem,
    EstadoMonitor,
    Link,
    ObservacaoLink,
    ObservacaoSite,
    ObservacaoSocket,
    Site,
    Socket,
    Snapshot,
)


def obs_link(nome="WAN1", tipo="WAN", online=True, socket="") -> ObservacaoLink:
    return ObservacaoLink(nome=nome, tipo=tipo, socket=socket, online=online)


def obs_socket(conectado=True, nome="primário") -> ObservacaoSocket:
    return ObservacaoSocket(nome=nome, conectado=conectado)


def obs_site(nome="Site A", conectado=True, sockets=None, **links) -> ObservacaoSite:
    """links: id=online(bool) ou id=ObservacaoLink. sockets: {chave: bool | ObservacaoSocket}."""
    ls = {}
    for lid, v in links.items():
        ls[lid] = v if isinstance(v, ObservacaoLink) else obs_link(nome=lid, online=v)
    ks = {k: v if isinstance(v, ObservacaoSocket) else obs_socket(conectado=v)
          for k, v in (sockets or {}).items()}
    return ObservacaoSite(nome=nome, conectado=conectado, links=ls, sockets=ks)


def ok(**sites) -> ConsultaOk:
    return ConsultaOk(snapshot=Snapshot(sites=sites))


def estado_base(*sites_ids, **kw) -> EstadoMonitor:
    return EstadoMonitor()


def estado_online(sockets=None, **sites) -> EstadoMonitor:
    """Estado pré-populado, tudo ONLINE: sites={id: ["L1", "L2"]}.

    sockets={id_site: {chave: nome}} acrescenta sockets ONLINE (site HA)."""
    est = EstadoMonitor()
    for sid, links in sites.items():
        est.sites[sid] = Site(
            nome=f"Site {sid}",
            links={l: Link(nome=l, tipo="WAN") for l in links},
        )
    for sid, ks in (sockets or {}).items():
        est.sites[sid].sockets = {k: Socket(nome=n) for k, n in ks.items()}
    return est


def tipos(eventos):
    return [e.tipo.value for e in eventos]


class Simulador:
    """Executa ciclos do motor puro, acumulando estado e eventos."""

    def __init__(self, cfg, relogio, estado=None):
        from cato_monitor.modelos import EstadoMonitor

        self.cfg, self.relogio = cfg, relogio
        self.estado = estado or EstadoMonitor()
        self.todos = []

    def ciclo(self, resultado, avancar=60):
        from cato_monitor.motor import avaliar_ciclo

        if avancar:
            self.relogio.avancar(avancar)
        self.estado, eventos = avaliar_ciclo(self.estado, resultado, self.relogio.agora(), self.cfg)
        for e in eventos:
            self.estado.filas[canal_do_evento(e).value].append(e)
        self.todos.extend(eventos)
        return eventos
