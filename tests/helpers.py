"""Construtores de observações e estados para os testes do motor."""

from cato_monitor.modelos import (
    ConsultaOk,
    EstadoItem,
    EstadoMonitor,
    Link,
    ObservacaoLink,
    ObservacaoSite,
    Site,
    Snapshot,
)


def obs_link(nome="WAN1", tipo="WAN", online=True, socket="") -> ObservacaoLink:
    return ObservacaoLink(nome=nome, tipo=tipo, socket=socket, online=online)


def obs_site(nome="Site A", conectado=True, **links) -> ObservacaoSite:
    """links: id=online(bool) ou id=ObservacaoLink."""
    ls = {}
    for lid, v in links.items():
        ls[lid] = v if isinstance(v, ObservacaoLink) else obs_link(nome=lid, online=v)
    return ObservacaoSite(nome=nome, conectado=conectado, links=ls)


def ok(**sites) -> ConsultaOk:
    return ConsultaOk(snapshot=Snapshot(sites=sites))


def estado_base(*sites_ids, **kw) -> EstadoMonitor:
    return EstadoMonitor()


def estado_online(**sites) -> EstadoMonitor:
    """Estado pré-populado, tudo ONLINE: sites={id: ["L1", "L2"]}."""
    est = EstadoMonitor()
    for sid, links in sites.items():
        est.sites[sid] = Site(
            nome=f"Site {sid}",
            links={l: Link(nome=l, tipo="WAN") for l in links},
        )
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
        self.estado.pendente_envio.extend(eventos)
        self.todos.extend(eventos)
        return eventos
