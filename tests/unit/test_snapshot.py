import copy
import json
from pathlib import Path

from cato_monitor.modelos import ConsultaFalhou
from cato_monitor.snapshot import normalizar

FIXTURES = Path(__file__).parents[1] / "fixtures" / "cato"


def carregar(nome):
    return json.loads((FIXTURES / f"{nome}.json").read_text(encoding="utf-8"))


def test_todos_online():
    snap = normalizar(carregar("todos_online"))
    assert set(snap.sites) == {"1", "2"}
    a = snap.sites["1"]
    assert a.nome == "Site A" and a.conectado
    assert {l.tipo for l in a.links.values()} == {"WAN", "LAN"}
    assert all(l.online for s in snap.sites.values() for l in s.links.values())
    assert a.links["s-1/WAN2"].nome == "WAN2 - Operadora Y"


def test_wan_offline():
    snap = normalizar(carregar("link_wan_offline"))
    offline = [(sid, lid) for sid, s in snap.sites.items() for lid, l in s.links.items() if not l.online]
    assert offline == [("1", "s-1/WAN2")]


def test_site_desconectado_nao_tem_observacao_de_links():
    snap = normalizar(carregar("site_desconectado"))
    assert not snap.sites["2"].conectado and snap.sites["2"].links == {}


def test_ha_chave_do_link_por_socket():
    snap = normalizar(carregar("site_ha"))
    links = snap.sites["3"].links
    assert {"s-3a/WAN1", "s-3b/WAN1", "s-3a/LAN1", "s-3b/LAN1"} == set(links)
    assert links["s-3a/WAN1"].socket == "primário" and links["s-3b/WAN1"].socket == "secundário"


def test_lista_de_sites_vazia_e_invalida_quando_o_estado_tem_sites():
    resp = {"data": {"accountSnapshot": {"sites": []}}}
    assert normalizar(resp, permitir_vazio=False) == ConsultaFalhou("schema_invalido")
    assert normalizar(resp, permitir_vazio=True).sites == {}


def test_estrutura_invalida():
    for resp in ({}, {"data": None}, {"data": {"accountSnapshot": {"sites": "x"}}},
                 {"data": {"accountSnapshot": {"sites": [{"id": "1", "connectivityStatus": "???"}]}}},
                 {"data": {"accountSnapshot": {"sites": [{"connectivityStatus": "connected"}]}}}):
        assert normalizar(resp) == ConsultaFalhou("schema_invalido")


def test_interface_sem_id_e_omitida():
    resp = carregar("todos_online")
    resp = copy.deepcopy(resp)
    resp["data"]["accountSnapshot"]["sites"][0]["devices"][0]["interfaces"][0].pop("id")
    snap = normalizar(resp)
    assert "s-1/WAN1" not in snap.sites["1"].links
    assert "s-1/WAN2" in snap.sites["1"].links


def test_site_conectado_sem_devices_e_omitido():
    resp = copy.deepcopy(carregar("todos_online"))
    resp["data"]["accountSnapshot"]["sites"][1]["devices"] = []
    snap = normalizar(resp)
    assert set(snap.sites) == {"1"}


def test_payload_real_anonimizado():
    """Estrutura real da conta (T007): LAN2 usada como WAN, HA com backup caído, site de nuvem."""
    snap = normalizar(carregar("real_anonimizado"))
    # site desativado sem devices não é monitorado
    assert "5" not in snap.sites
    # LAN2 com destType CATO é WAN (vem em device.interfaces)
    lan2 = [l for l in snap.sites["1"].links.values() if l.nome.startswith("LAN2")]
    assert lan2 and all(l.tipo == "WAN" for l in lan2)
    # HA: socket caído gera links offline só para ele
    ha = snap.sites["2"].links
    assert len({lid.split("/")[0] for lid in ha}) == 2  # um conjunto de links por socket
    assert any(not l.online for l in ha.values()) and any(l.online for l in ha.values())
    # WAN caída permanece no payload com connected=false
    assert any(not l.online and l.tipo == "WAN" for l in snap.sites["3"].links.values())
    # site desconectado e ativo continua observado
    assert not snap.sites["4"].conectado
    # só portas com papel LAN viram link LAN
    assert all(l.tipo in ("WAN", "LAN") for s in snap.sites.values() for l in s.links.values())


def test_site_desativado_nao_e_monitorado():
    resp = copy.deepcopy(carregar("todos_online"))
    resp["data"]["accountSnapshot"]["sites"][1]["operationalStatus"] = "disabled"
    assert set(normalizar(resp).sites) == {"1"}


def test_porta_desativada_nao_vira_link_lan():
    resp = copy.deepcopy(carregar("todos_online"))
    s = resp["data"]["accountSnapshot"]["sites"][0]
    for i in s["info"]["interfaces"]:
        if i["id"] == "LAN1":
            i["destType"] = "INTERFACE_DISABLED"
    assert not any(l.tipo == "LAN" for l in normalizar(resp).sites["1"].links.values())
