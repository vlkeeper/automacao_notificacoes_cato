"""Sockets de sites HA no motor (feature 004, data-model §3)."""

from cato_monitor.modelos import EstadoItem, verificar_invariantes

from ..helpers import Simulador, estado_online, obs_site, obs_socket, ok, tipos

SOCKETS = {"s1": "primário", "s2": "secundário"}


def sim(cfg, relogio):
    est = estado_online(sockets={"A": SOCKETS}, A=["s1/W1", "s1/L1", "s2/W1", "s2/L1"])
    return Simulador(cfg, relogio, est)


def ha(c1=True, c2=True, w1=True, l1=True, w2=True, l2=True, **extra):
    """Site HA: s1/s2 conectados ou não; as portas de um socket desconectado vêm offline."""
    return ok(A=obs_site(
        "Site A",
        sockets={"s1": obs_socket(c1, "primário"), "s2": obs_socket(c2, "secundário")},
        **{"s1/W1": w1 and c1, "s1/L1": l1 and c1, "s2/W1": w2 and c2, "s2/L1": l2 and c2},
        **extra,
    ))


def rodar(s, n, **kw):
    eventos = []
    for _ in range(n):
        eventos += s.ciclo(ha(**kw))
    return eventos


def soquete(s, kid):
    return s.estado.sites["A"].sockets[kid]


def test_queda_do_socket_gera_um_unico_aviso_e_silencia_as_portas(cfg, relogio):
    s = sim(cfg, relogio)
    assert rodar(s, 3, c2=False) == []                      # pendente, dentro da tolerância
    assert soquete(s, "s2").estado == EstadoItem.PENDENTE_OFFLINE
    ev = rodar(s, 1, c2=False)                              # 180 s: notifica
    assert tipos(ev) == ["SOCKET_OFFLINE"]
    d = ev[0].dados
    assert d["socket"] == "secundário" and d["socket_id"] == "s2" and d["site_nome"] == "Site A"
    assert rodar(s, 5, c2=False) == []                      # sem LINK_OFFLINE nem repetição
    assert all(l.estado == EstadoItem.ONLINE for k, l in s.estado.sites["A"].links.items()
               if k.startswith("s2/"))
    assert not verificar_invariantes(s.estado)


def test_pendente_nao_emite_antes_da_tolerancia_e_porta_pendente_volta_a_online(cfg, relogio):
    s = sim(cfg, relogio)
    assert rodar(s, 2, c2=False) == []
    assert s.estado.sites["A"].links["s2/W1"].estado == EstadoItem.PENDENTE_OFFLINE
    rodar(s, 2, c2=False)
    assert s.estado.sites["A"].links["s2/W1"].estado == EstadoItem.ONLINE


def test_porta_ja_notificada_fica_inalterada_e_silenciada(cfg, relogio):
    s = sim(cfg, relogio)
    est_link = s.estado.sites["A"].links["s2/W1"]
    est_link.estado, est_link.notificado = EstadoItem.OFFLINE_NOTIFICADO, True
    est_link.inicio_queda = relogio.agora()
    ev = rodar(s, 6, c2=False)
    assert tipos(ev) == ["SOCKET_OFFLINE"]
    assert s.estado.sites["A"].links["s2/W1"].estado == EstadoItem.OFFLINE_NOTIFICADO


def test_porta_de_socket_offline_cai_e_volta_sem_aviso(cfg, relogio):
    s = sim(cfg, relogio)
    rodar(s, 4, c2=False)
    assert tipos(rodar(s, 4, c2=False, w2=False)) == []
    assert tipos(rodar(s, 4, c2=False, w2=True)) == []


def test_socket_sem_observacao_fica_inalterado(cfg, relogio):
    s = sim(cfg, relogio)
    rodar(s, 4, c2=False)
    s.ciclo(ok(A=obs_site("Site A", sockets={"s1": True}, **{"s1/W1": True, "s1/L1": True})))
    assert soquete(s, "s2").estado == EstadoItem.OFFLINE_NOTIFICADO
    assert soquete(s, "s2").ausencias == 1


def test_socket_ausente_por_3_ciclos_e_removido_sem_aviso(cfg, relogio):
    s = sim(cfg, relogio)
    for _ in range(3):
        assert s.ciclo(ok(A=obs_site("Site A", sockets={"s1": True}, **{"s1/W1": True, "s1/L1": True}))) == []
    assert "s2" not in s.estado.sites["A"].sockets


def test_os_dois_sockets_caem_e_o_aviso_e_so_do_site(cfg, relogio):
    s = sim(cfg, relogio)
    eventos = []
    for _ in range(5):
        eventos += s.ciclo(ha(c1=False, c2=False))
    assert tipos(eventos) == ["SITE_OFFLINE"]
    for k in ("s1", "s2"):
        assert soquete(s, k).coberto_pelo_site and soquete(s, k).estado == EstadoItem.OFFLINE_NOTIFICADO
    assert not verificar_invariantes(s.estado)


def test_queda_do_socket_e_adiada_com_o_site_pendente(cfg, relogio):
    s = sim(cfg, relogio)
    assert rodar(s, 2, c2=False) == []                       # s2 pendente desde t+60
    # s1 também cai (portas offline, socket conectado): o site fica pendente em t+180
    eventos = rodar(s, 1, c2=False, w1=False, l1=False)
    eventos += rodar(s, 1, c2=False, w1=False, l1=False)     # t+240: QUEDA de s2 seria agora
    assert eventos == []
    assert soquete(s, "s2").estado == EstadoItem.PENDENTE_OFFLINE
    eventos = rodar(s, 3, c2=False, w1=False, l1=False)      # site confirma a queda
    assert tipos(eventos) == ["SITE_OFFLINE"]


def test_retorno_do_socket_gera_um_aviso_e_fecha_portas_sem_aviso(cfg, relogio):
    s = sim(cfg, relogio)
    rodar(s, 4, c2=False)
    ev = rodar(s, 1)                                    # socket volta com as portas online
    assert tipos(ev) == ["SOCKET_RETORNO"]
    d = ev[0].dados
    assert d["socket"] == "secundário" and d["inicio_queda"] and d["retorno_em"]
    assert soquete(s, "s2").estado == EstadoItem.ONLINE
    assert all(l.estado == EstadoItem.ONLINE for l in s.estado.sites["A"].links.values())
    assert rodar(s, 3) == []
    assert not verificar_invariantes(s.estado)


def test_retorno_do_socket_com_porta_ainda_fora_mantem_a_porta_aberta(cfg, relogio):
    s = sim(cfg, relogio)
    link = s.estado.sites["A"].links["s2/W1"]
    link.estado, link.notificado, link.inicio_queda = EstadoItem.OFFLINE_NOTIFICADO, True, relogio.agora()
    rodar(s, 4, c2=False)
    assert tipos(rodar(s, 1, w2=False)) == ["SOCKET_RETORNO"]   # W1 segue fora
    assert s.estado.sites["A"].links["s2/W1"].estado == EstadoItem.OFFLINE_NOTIFICADO
    assert tipos(rodar(s, 2, w2=False)) == []                    # sem novo LINK_OFFLINE
    assert tipos(rodar(s, 1)) == ["LINK_RETORNO"]                # retorno posterior é avisado


def test_porta_online_com_socket_de_volta_e_offline_segue_tolerancia(cfg, relogio):
    s = sim(cfg, relogio)
    rodar(s, 4, c2=False)
    assert tipos(rodar(s, 1, w2=False)) == ["SOCKET_RETORNO"]
    assert s.estado.sites["A"].links["s2/W1"].estado == EstadoItem.PENDENTE_OFFLINE
    assert tipos(rodar(s, 3, w2=False)) == ["LINK_OFFLINE"]


def test_site_offline_absorve_socket_ja_avisado(cfg, relogio):
    s = sim(cfg, relogio)
    assert tipos(rodar(s, 4, c2=False)) == ["SOCKET_OFFLINE"]
    ev = rodar(s, 5, c1=False, c2=False)
    assert tipos(ev) == ["SITE_OFFLINE"]
    assert soquete(s, "s2").coberto_pelo_site and soquete(s, "s2").notificado
    assert soquete(s, "s1").coberto_pelo_site
    assert rodar(s, 3, c1=False, c2=False) == []             # site offline: sockets não avaliados


def test_retorno_do_site_com_um_socket_gera_site_de_volta_e_socket_offline(cfg, relogio):
    s = sim(cfg, relogio)
    rodar(s, 5, c1=False, c2=False)
    ev = rodar(s, 1, c2=False)
    assert tipos(ev) == ["SITE_RETORNO", "SOCKET_OFFLINE"]
    assert ev[0].dados["links_ainda_offline"] == []
    assert ev[1].dados["socket"] == "secundário"
    assert soquete(s, "s1").estado == EstadoItem.ONLINE
    assert soquete(s, "s2").estado == EstadoItem.OFFLINE_NOTIFICADO and not soquete(s, "s2").coberto_pelo_site
    assert tipos(rodar(s, 2, c2=False)) == []
    assert tipos(rodar(s, 1)) == ["SOCKET_RETORNO"]
    assert not verificar_invariantes(s.estado)


def test_retorno_do_site_com_os_dois_sockets_gera_so_site_de_volta(cfg, relogio):
    s = sim(cfg, relogio)
    rodar(s, 5, c1=False, c2=False)
    assert tipos(rodar(s, 1)) == ["SITE_RETORNO"]
    assert all(k.estado == EstadoItem.ONLINE for k in s.estado.sites["A"].sockets.values())


def test_socket_coberto_sem_observacao_segue_coberto(cfg, relogio):
    s = sim(cfg, relogio)
    rodar(s, 5, c1=False, c2=False)
    ev = s.ciclo(ok(A=obs_site("Site A", sockets={"s1": True}, **{"s1/W1": True, "s1/L1": True})))
    assert tipos(ev) == ["SITE_RETORNO"]
    assert soquete(s, "s2").coberto_pelo_site and soquete(s, "s2").estado == EstadoItem.OFFLINE_NOTIFICADO


def test_site_sem_ha_nao_tem_sockets(cfg, relogio):
    s = Simulador(cfg, relogio, estado_online(A=["W1", "W2"]))
    for _ in range(5):
        s.ciclo(ok(A=obs_site("Site A", W1=False, W2=True)))
    assert s.estado.sites["A"].sockets == {}
    assert [e.tipo.value for e in s.todos] == ["LINK_OFFLINE"]
