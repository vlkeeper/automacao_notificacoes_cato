"""Normaliza a resposta GraphQL da Cato num `Snapshot`.

ÚNICO ponto que conhece o schema da Cato. ATENÇÃO (tasks T007, R-001): o papel LAN/WAN das
portas e o comportamento de uma WAN caída ainda NÃO foram verificados contra a conta real. As
regras marcadas com ⚠ abaixo seguem o contrato "candidato" e devem ser revistas com os payloads
reais, sem tocar na máquina de estados.
"""

from __future__ import annotations

from typing import Any

from .modelos import ConsultaFalhou, ObservacaoLink, ObservacaoSite, Snapshot

STATUS_CONECTADO = "connected"
STATUS_DESCONECTADO = "disconnected"


class _SchemaInvalido(Exception):
    pass


def _rotulo_socket(device: dict[str, Any]) -> str:
    info = device.get("socketInfo") or {}
    if info.get("isPrimary") is True or device.get("haRole") == "PRIMARY":
        return "primário"
    if info.get("isPrimary") is False or device.get("haRole") == "SECONDARY":
        return "secundário"
    return ""


def _links_do_device(device: dict[str, Any]) -> dict[str, ObservacaoLink]:
    info = device.get("socketInfo") or {}
    chave_socket = info.get("id") or device.get("id")
    if not chave_socket:
        return {}
    socket = _rotulo_socket(device)
    links: dict[str, ObservacaoLink] = {}

    # WAN: túnel da porta com a Cato. ⚠ papel e "WAN caída some?" a confirmar (R-001).
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

    # LAN: link físico. ⚠ papel LAN inferido pelo prefixo do id até a verificação (R-001).
    for porta in device.get("interfacesLinkState") or []:
        iid = porta.get("id")
        if not iid or iid in ids_wan or not str(iid).upper().startswith("LAN"):
            continue
        links[f"{chave_socket}/{iid}"] = ObservacaoLink(
            nome=str(iid), tipo="LAN", socket=socket, online=porta.get("up") is True,
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
        nome = ((s.get("info") or {}).get("name"))
        devices = s.get("devices")

        if not nome:
            continue  # sem nome: observação inválida, estado inalterado
        if conectado and not devices:
            continue  # site conectado sem devices: observação inválida (omitido)

        links: dict[str, ObservacaoLink] = {}
        for device in devices or []:  # site desconectado sem devices: links sem observação
            links.update(_links_do_device(device))
        sites[str(s["id"])] = ObservacaoSite(nome=nome, conectado=conectado, links=links)
    return Snapshot(sites=sites)
