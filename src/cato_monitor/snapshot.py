"""Normaliza a resposta GraphQL da Cato num `Snapshot`.

ÚNICO ponto que conhece o schema da Cato. Regras verificadas contra a conta real (T007, R-001):
- o papel das portas vem de `site.info.interfaces[].destType` (`CATO` = WAN; `LAN`/`VRRP_AND_LAN`
  = LAN; `INTERFACE_DISABLED` = ignorada);
- uma WAN caída continua em `device.interfaces` com `connected=false` (não some);
- `interfacesLinkState` vem vazio quando o device está desconectado;
- só sites com `operationalStatus == "active"` são monitorados (os demais estão desativados).
"""

from __future__ import annotations

from typing import Any

from .modelos import ConsultaFalhou, ObservacaoLink, ObservacaoSite, ObservacaoSocket, Snapshot

STATUS_CONECTADO = "connected"
STATUS_DESCONECTADO = "disconnected"
STATUS_OPERACIONAL_ATIVO = "active"
# VRRP = porta "HA link" entre os dois sockets de um par HA (monitorada como link LAN).
DEST_TYPES_LAN = frozenset({"LAN", "VRRP_AND_LAN", "LAN_AND_HA", "LAN_LAG_MASTER", "VRRP"})


class _SchemaInvalido(Exception):
    pass


def _rotulo_socket(device: dict[str, Any], site_ha: bool) -> str:
    """Primário/secundário do socket. Em HA a fonte de verdade é `socketInfo.isPrimary`.

    `haRole` NÃO serve para isso: na conta real os dois sockets de um par HA vêm com `MASTER`.
    """
    info = device.get("socketInfo") or {}
    if site_ha and isinstance(info.get("isPrimary"), bool):
        return "primário" if info["isPrimary"] else "secundário"
    papel = str(device.get("haRole") or "").upper()
    if papel in ("MASTER", "PRIMARY"):
        return "primário"
    if papel in ("BACKUP", "SECONDARY"):
        return "secundário"
    return ""


def _socket_do_device(device: dict[str, Any], site_ha: bool) -> tuple[str, ObservacaoSocket] | None:
    """Observação do socket (R-001): `device.connected` quando booleano; sem o campo, só conta como
    desconectado se há ≥ 1 WAN observada e todas estão offline. LAN/"HA link" não entram."""
    info = device.get("socketInfo") or {}
    chave = info.get("id") or device.get("id")
    if not chave:
        return None
    if isinstance(device.get("connected"), bool):
        conectado = device["connected"]
    else:
        wans = [i for i in device.get("interfaces") or [] if i.get("id")]
        conectado = not (wans and all(i.get("connected") is not True for i in wans))
    nome = _rotulo_socket(device, site_ha) or info.get("serial") or str(chave)
    return str(chave), ObservacaoSocket(nome=nome, conectado=conectado)


def _links_do_device(
    device: dict[str, Any], ids_lan: Any, site_ha: bool = False
) -> dict[str, ObservacaoLink]:
    info = device.get("socketInfo") or {}
    chave_socket = info.get("id") or device.get("id")
    if not chave_socket:
        return {}
    socket = _rotulo_socket(device, site_ha)
    links: dict[str, ObservacaoLink] = {}

    # WAN: túnel da porta com a Cato; WAN caída permanece na lista com connected=false.
    ids_wan = set()
    for iface in device.get("interfaces") or []:
        iid = iface.get("id")
        if not iid:
            continue  # interface sem id: item omitido (observação inválida)
        ids_wan.add(iid)
        links[f"{chave_socket}/{iid}"] = ObservacaoLink(
            nome=iface.get("name") or iid, tipo="WAN", socket=socket,
            online=iface.get("connected") is True,
        )

    # LAN: link físico das portas com papel LAN (destType em info.interfaces).
    for porta in device.get("interfacesLinkState") or []:
        iid = porta.get("id")
        if not iid or iid in ids_wan or iid not in ids_lan:
            continue
        links[f"{chave_socket}/{iid}"] = ObservacaoLink(
            nome=ids_lan.get(iid) or str(iid), tipo="LAN", socket=socket, online=porta.get("up") is True,
        )
    return links


def normalizar(resposta: Any, permitir_vazio: bool = True) -> Snapshot | ConsultaFalhou:
    """Converte o JSON da Cato em Snapshot, ou `ConsultaFalhou("schema_invalido")`.

    `permitir_vazio=False` (o estado já conhece sites): lista de sites vazia é inválida, pois uma
    conta não perde todos os sites de uma vez.
    """
    try:
        sites_json = resposta["data"]["accountSnapshot"]["sites"]
    except (KeyError, TypeError):
        return ConsultaFalhou("schema_invalido")
    if not isinstance(sites_json, list):
        return ConsultaFalhou("schema_invalido")
    if not sites_json and not permitir_vazio:
        return ConsultaFalhou("schema_invalido")

    sites: dict[str, ObservacaoSite] = {}
    for s in sites_json:
        if not isinstance(s, dict) or not s.get("id"):
            return ConsultaFalhou("schema_invalido")
        status = s.get("connectivityStatus")
        if status not in (STATUS_CONECTADO, STATUS_DESCONECTADO):
            return ConsultaFalhou("schema_invalido")
        conectado = status == STATUS_CONECTADO
        info = s.get("info") or {}
        nome = info.get("name")
        devices = s.get("devices")
        if s.get("operationalStatus") != STATUS_OPERACIONAL_ATIVO:
            continue  # site desativado/em implantação: não monitorado
        # id da porta LAN -> nome como vem da API (ex.: "LAN 01", "HA link")
        ids_lan = {
            i["id"]: i.get("name")
            for i in (info.get("interfaces") or [])
            if isinstance(i, dict) and i.get("id") and i.get("destType") in DEST_TYPES_LAN
        }

        if not nome:
            continue  # sem nome: observação inválida, estado inalterado
        if conectado and not devices:
            continue  # site conectado sem devices: observação inválida (omitido)

        # Site HA: isHA ou mais de um device (R-002). Só ele tem sockets observados.
        site_ha = info.get("isHA") is True or len(devices or []) > 1
        links: dict[str, ObservacaoLink] = {}
        sockets: dict[str, ObservacaoSocket] = {}
        for device in devices or []:  # site desconectado sem devices: links sem observação
            links.update(_links_do_device(device, ids_lan, site_ha=site_ha))
            if site_ha and (par := _socket_do_device(device, site_ha)):
                sockets[par[0]] = par[1]
        sites[str(s["id"])] = ObservacaoSite(nome=nome, conectado=conectado, links=links, sockets=sockets)
    return Snapshot(sites=sites)
