"""Motor do ciclo: compõe as transições de sites e links (data-model §3.2).

`avaliar_ciclo` é PURA: sem I/O, sem relógio global. Recebe o estado, o resultado da consulta e
`agora`; devolve um novo estado (o original não é alterado) e os eventos gerados, já com id.
Os eventos ainda NÃO estão na fila `pendente_envio`: quem chama (o daemon) os anexa e persiste.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from .config import Config
from .modelos import (
    LIMITE_AUSENCIAS,
    LIMITE_FALHAS,
    BYTES_POR_LINHA,
    MAX_PENDENCIAS_POR_CARD,
    ORCAMENTO_BYTES_LEMBRETE,
    ConsultaFalhou,
    ConsultaOk,
    EstadoItem,
    EstadoMonitor,
    EventoNotificacao,
    Link,
    ObservacaoLink,
    ObservacaoSite,
    Origem,
    ResultadoConsulta,
    Site,
    TipoEvento,
    ts_para_str,
)
from .transicoes import TipoAcao, proximo_estado


@dataclass
class Detalhes:
    """Informações para log (o motor não loga): transições e registros de inventário."""

    transicoes: list[dict[str, Any]] = field(default_factory=list)
    registros: list[dict[str, Any]] = field(default_factory=list)


def _site_offline(obs: ObservacaoSite) -> bool:
    """Site observado offline: desconectado OU (≥ 1 link monitorado e todos offline)."""
    if not obs.conectado:
        return True
    return bool(obs.links) and all(not l.online for l in obs.links.values())


def _item_baseline(obs_offline: bool, agora: datetime) -> dict[str, Any]:
    if obs_offline:
        return dict(
            estado=EstadoItem.OFFLINE_NOTIFICADO, inicio_queda=agora, notificado=True,
            origem=Origem.LINHA_BASE,
        )
    return dict(estado=EstadoItem.ONLINE, inicio_queda=None, notificado=False)


def _novo_link(obs: ObservacaoLink, agora: datetime) -> Link:
    return Link(nome=obs.nome, tipo=obs.tipo, socket=obs.socket, **_item_baseline(not obs.online, agora))


def _novo_site(obs: ObservacaoSite, agora: datetime) -> Site:
    site = Site(nome=obs.nome, **_item_baseline(_site_offline(obs), agora))
    site.links = {lid: _novo_link(l, agora) for lid, l in obs.links.items()}
    return site


def _limpar_link(link: Link) -> Link:
    return replace(link, estado=EstadoItem.ONLINE, inicio_queda=None, notificado=False,
                   coberto_pelo_site=False)


def avaliar_ciclo(
    estado: EstadoMonitor, resultado: ResultadoConsulta, agora: datetime, cfg: Config
) -> tuple[EstadoMonitor, list[EventoNotificacao]]:
    novo, eventos, _ = avaliar_ciclo_detalhado(estado, resultado, agora, cfg)
    return novo, eventos


def avaliar_ciclo_detalhado(
    estado: EstadoMonitor, resultado: ResultadoConsulta, agora: datetime, cfg: Config
) -> tuple[EstadoMonitor, list[EventoNotificacao], Detalhes]:
    est = copy.deepcopy(estado)
    det = Detalhes()
    pendentes: list[tuple[TipoEvento, dict[str, Any]]] = []
    mon = est.monitor
    tol = timedelta(seconds=cfg.tolerancia_segundos)

    def emitir(tipo: TipoEvento, **dados: Any) -> None:
        pendentes.append((tipo, dados))

    # 1. Falha de consulta: só o contador do monitor muda; os itens ficam intocados.
    if isinstance(resultado, ConsultaFalhou):
        mon.falhas_consecutivas += 1
        if mon.falhas_consecutivas >= LIMITE_FALHAS and not mon.alerta_falha_enviado:
            mon.alerta_falha_enviado = True
            emitir(
                TipoEvento.MONITOR_FALHA,
                falhas_consecutivas=mon.falhas_consecutivas,
                desde=ts_para_str(mon.ultima_consulta_ok_em or agora),
                ultimo_motivo=resultado.motivo,
            )
        return _finalizar(est, pendentes, agora), _eventos(est, pendentes, agora), det

    # 2. Consulta ok.
    snap = resultado.snapshot
    if mon.alerta_falha_enviado:
        emitir(
            TipoEvento.MONITOR_RECUPERADO,
            desde=ts_para_str(mon.ultima_consulta_ok_em or agora),
            recuperado_em=ts_para_str(agora),
            falhas_total=mon.falhas_consecutivas,
        )
    mon.falhas_consecutivas = 0
    mon.alerta_falha_enviado = False
    mon.ultima_consulta_ok_em = agora

    hoje_local = agora.astimezone(cfg.tz).date().isoformat()
    passou_horario = agora.astimezone(cfg.tz).time() >= cfg.lembrete_horario

    # 3. Linha de base (estado novo/corrompido): registra tudo e resume num único aviso.
    if not est.sites and snap.sites:
        for sid in sorted(snap.sites):
            est.sites[sid] = _novo_site(snap.sites[sid], agora)
        itens_offline = []
        links_total = 0
        for site in est.sites.values():
            links_total += len(site.links)
            if site.estado == EstadoItem.OFFLINE_NOTIFICADO:
                itens_offline.append({"site_nome": site.nome, "link_nome": None, "tipo": "SITE"})
            for link in site.links.values():
                if link.estado == EstadoItem.OFFLINE_NOTIFICADO:
                    itens_offline.append({"site_nome": site.nome, "link_nome": link.nome, "tipo": link.tipo})
        emitir(
            TipoEvento.MONITOR_INICIADO,
            sites_total=len(est.sites), links_total=links_total, itens_offline=itens_offline,
        )
        if passou_horario:
            mon.ultimo_lembrete_data = hoje_local  # o resumo já cobre o lembrete de hoje
        return _finalizar(est, pendentes, agora), _eventos(est, pendentes, agora), det

    # 4–6. Inventário e avaliação, em ordem determinística de site_id.
    for sid in sorted(set(est.sites) | set(snap.sites)):
        site = est.sites.get(sid)
        obs = snap.sites.get(sid)

        if site is None:  # item novo: linha de base individual, sem aviso
            est.sites[sid] = _novo_site(obs, agora)
            det.registros.append({"event": "item_novo", "site_id": sid, "link_id": None})
            continue

        if obs is None:  # ausente numa resposta válida: observação inválida
            site.ausencias += 1
            if site.ausencias >= LIMITE_AUSENCIAS:
                del est.sites[sid]
                det.registros.append({"event": "item_removido", "site_id": sid, "link_id": None})
            continue

        site.ausencias = 0
        site.nome = obs.nome
        _avaliar_site(sid, site, obs, agora, tol, emitir, det)

    # 7. Lembrete diário.
    if passou_horario and mon.ultimo_lembrete_data != hoje_local:
        mon.ultimo_lembrete_data = hoje_local
        pendencias = _pendencias(est)
        if pendencias:
            partes = _dividir_pendencias(pendencias)
            for i, parte in enumerate(partes):
                emitir(TipoEvento.LEMBRETE_DIARIO, data_local=hoje_local, pendencias=parte,
                       parte=i + 1, total_partes=len(partes))

    return _finalizar(est, pendentes, agora), _eventos(est, pendentes, agora), det


# --------------------------------------------------------------------------- internos


def _finalizar(est: EstadoMonitor, pendentes, agora: datetime) -> EstadoMonitor:
    """Reserva os ids dos eventos (proximo_seq) no estado devolvido."""
    est.monitor.proximo_seq += len(pendentes)
    return est


def _eventos(est: EstadoMonitor, pendentes, agora: datetime) -> list[EventoNotificacao]:
    primeiro = est.monitor.proximo_seq - len(pendentes)
    return [
        EventoNotificacao(
            id=f"evt-{primeiro + i:06d}", tipo=tipo, ocorrido_em=agora, criado_em=agora, dados=dados
        )
        for i, (tipo, dados) in enumerate(pendentes)
    ]


def _pendencias(est: EstadoMonitor) -> list[dict[str, Any]]:
    itens: list[dict[str, Any]] = []
    for sid in sorted(est.sites):
        site = est.sites[sid]
        if site.estado == EstadoItem.OFFLINE_NOTIFICADO:
            itens.append({"site_nome": site.nome, "link_nome": None, "tipo": "SITE",
                          "inicio_queda": ts_para_str(site.inicio_queda)})
        for lid in sorted(site.links):
            link = site.links[lid]
            if link.estado == EstadoItem.OFFLINE_NOTIFICADO and not link.coberto_pelo_site:
                itens.append({"site_nome": site.nome, "link_nome": link.nome, "tipo": link.tipo,
                              "inicio_queda": ts_para_str(link.inicio_queda)})
    return itens


def _dividir_pendencias(pendencias: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Agrupa pendências em cards de, no máximo, ORCAMENTO_BYTES_LEMBRETE (estimado) cada."""
    partes: list[list[dict[str, Any]]] = [[]]
    usado = 0
    for p in pendencias:
        custo = BYTES_POR_LINHA + 2 * len((p["site_nome"] + (p["link_nome"] or "")).encode("utf-8"))
        if partes[-1] and (usado + custo > ORCAMENTO_BYTES_LEMBRETE or len(partes[-1]) >= MAX_PENDENCIAS_POR_CARD):
            partes.append([])
            usado = 0
        partes[-1].append(p)
        usado += custo
    return partes


def _transicao(det: Detalhes, item: str, sid: str, lid: str | None, de: EstadoItem, para: EstadoItem) -> None:
    if de != para:
        det.transicoes.append(
            {"item": item, "site_id": sid, "link_id": lid, "de": de.value, "para": para.value}
        )


def _avaliar_site(sid, site: Site, obs: ObservacaoSite, agora, tol, emitir, det: Detalhes) -> None:
    # --- inventário de links (só avança ausência com o site conectado)
    for lid, lobs in obs.links.items():
        if lid not in site.links:
            site.links[lid] = _novo_link(lobs, agora)
            det.registros.append({"event": "item_novo", "site_id": sid, "link_id": lid})
        else:
            link = site.links[lid]
            link.ausencias = 0
            link.nome, link.tipo, link.socket = lobs.nome, lobs.tipo, lobs.socket
    if obs.conectado:
        for lid in [l for l in site.links if l not in obs.links]:
            site.links[lid].ausencias += 1
            if site.links[lid].ausencias >= LIMITE_AUSENCIAS:
                del site.links[lid]
                det.registros.append({"event": "item_removido", "site_id": sid, "link_id": lid})

    # --- site (passo 5)
    estado_antes = site.estado
    novo, acoes = proximo_estado(site, _site_offline(obs), agora, tol)
    site.estado, site.inicio_queda, site.notificado = novo.estado, novo.inicio_queda, novo.notificado
    _transicao(det, "site", sid, None, estado_antes, site.estado)

    tratados: set[str] = set()
    recem_notificado = False
    for acao in acoes:
        if acao.tipo == TipoAcao.QUEDA:
            recem_notificado = True
            afetados = []
            for lid, link in site.links.items():
                lobs = obs.links.get(lid)
                offline_agora = lobs is not None and not lobs.online
                if link.estado != EstadoItem.ONLINE or offline_agora:
                    de = link.estado
                    link.estado = EstadoItem.OFFLINE_NOTIFICADO
                    link.coberto_pelo_site = True
                    link.notificado = True
                    link.inicio_queda = link.inicio_queda or site.inicio_queda
                    _transicao(det, "link", sid, lid, de, link.estado)
                    afetados.append([link.nome, link.tipo])
                tratados.add(lid)
            if not obs.conectado:
                afetados = [[l.nome, l.tipo] for l in site.links.values()]
            emitir(
                TipoEvento.SITE_OFFLINE, site_id=sid, site_nome=site.nome,
                inicio_queda=ts_para_str(site.inicio_queda),
                motivo="desconectado_cato" if not obs.conectado else "todos_links_inativos",
                links_afetados=afetados,
            )
        else:  # RETORNO do site
            ainda_fora = []
            for lid, link in site.links.items():
                if not link.coberto_pelo_site:
                    continue
                tratados.add(lid)
                lobs = obs.links.get(lid)
                de = link.estado
                if lobs is not None and lobs.online:
                    site.links[lid] = _limpar_link(link)
                elif lobs is not None:
                    link.coberto_pelo_site = False
                    ainda_fora.append([link.nome, link.tipo, ts_para_str(link.inicio_queda)])
                else:
                    link.coberto_pelo_site = False
                _transicao(det, "link", sid, lid, de, site.links[lid].estado)
            emitir(
                TipoEvento.SITE_RETORNO, site_id=sid, site_nome=site.nome,
                inicio_queda=ts_para_str(agora - acao.duracao),
                retorno_em=ts_para_str(agora), links_ainda_offline=ainda_fora,
            )

    # --- links (passo 6)
    if site.estado == EstadoItem.OFFLINE_NOTIFICADO:
        if not recem_notificado:
            _links_sob_site_offline(sid, site, obs, agora, det)
        return

    for lid in sorted(site.links):
        if lid in tratados:
            continue
        link = site.links[lid]
        lobs = obs.links.get(lid)
        obs_offline = None if lobs is None else not lobs.online
        antes = link.estado
        novo_link, acoes_l = proximo_estado(link, obs_offline, agora, tol)
        if site.estado == EstadoItem.PENDENTE_OFFLINE and any(a.tipo == TipoAcao.QUEDA for a in acoes_l):
            continue  # adia: reavalia no próximo ciclo, quando o site já estiver decidido
        site.links[lid] = novo_link
        _transicao(det, "link", sid, lid, antes, novo_link.estado)
        for acao in acoes_l:
            if acao.tipo == TipoAcao.QUEDA:
                outros = sum(1 for k, o in obs.links.items() if k != lid and o.online)
                emitir(
                    TipoEvento.LINK_OFFLINE, site_id=sid, site_nome=site.nome, link_id=lid,
                    link_nome=novo_link.nome, link_tipo=novo_link.tipo,
                    inicio_queda=ts_para_str(novo_link.inicio_queda), outros_links_online=outros,
                )
            else:
                emitir(
                    TipoEvento.LINK_RETORNO, site_id=sid, site_nome=site.nome, link_id=lid,
                    link_nome=novo_link.nome, link_tipo=novo_link.tipo,
                    inicio_queda=ts_para_str(agora - acao.duracao), retorno_em=ts_para_str(agora),
                )


def _links_sob_site_offline(sid, site: Site, obs: ObservacaoSite, agora, det: Detalhes) -> None:
    """Site já notificado e ainda offline: links só têm o estado atualizado, sem avisos."""
    for lid in sorted(site.links):
        link = site.links[lid]
        lobs = obs.links.get(lid)
        if lobs is None:
            continue
        de = link.estado
        if not lobs.online:
            if link.estado == EstadoItem.ONLINE:
                link.inicio_queda = agora
            link.estado = EstadoItem.OFFLINE_NOTIFICADO
            link.notificado = True
            link.coberto_pelo_site = True
        elif link.estado != EstadoItem.ONLINE:
            site.links[lid] = _limpar_link(link)
        _transicao(det, "link", sid, lid, de, site.links[lid].estado)
