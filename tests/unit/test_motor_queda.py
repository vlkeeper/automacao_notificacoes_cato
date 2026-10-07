from cato_monitor.modelos import ConsultaFalhou, EstadoItem, TipoEvento

from ..helpers import Simulador, estado_online, obs_site, ok, tipos


def sim(cfg, relogio, **sites):
    return Simulador(cfg, relogio, estado_online(**sites))


def test_link_caido_gera_um_link_offline_apos_tolerancia(cfg, relogio):
    s = sim(cfg, relogio, A=["W1", "W2"])
    quedas = lambda: ok(A=obs_site("Site A", W1=False, W2=True))
    assert s.ciclo(quedas()) == []               # t+60: PENDENTE
    assert s.ciclo(quedas()) == []               # t+120
    assert s.ciclo(quedas()) == []               # t+180: 120 s de queda
    ev = s.ciclo(quedas())                       # t+240: 180 s => notifica
    assert tipos(ev) == ["LINK_OFFLINE"]
    d = ev[0].dados
    assert d["site_nome"] == "Site A" and d["link_nome"] == "W1" and d["outros_links_online"] == 1
    assert s.ciclo(quedas()) == []               # um aviso por episódio
    assert s.estado.sites["A"].links["W1"].estado == EstadoItem.OFFLINE_NOTIFICADO


def test_todos_os_links_offline_gera_site_offline_e_suprime_links(cfg, relogio):
    s = sim(cfg, relogio, A=["W1", "W2"])
    caido = lambda: ok(A=obs_site("Site A", W1=False, W2=False))
    eventos = []
    for _ in range(5):
        eventos += s.ciclo(caido())
    assert tipos(eventos) == ["SITE_OFFLINE"]
    assert eventos[0].dados["motivo"] == "todos_links_inativos"
    site = s.estado.sites["A"]
    assert all(l.coberto_pelo_site and l.notificado for l in site.links.values())
    assert all(l.inicio_queda is not None for l in site.links.values())
    assert len(eventos[0].dados["links_afetados"]) == 2


def test_site_desconectado_gera_site_offline_desconectado_cato(cfg, relogio):
    s = sim(cfg, relogio, A=["W1"])
    eventos = []
    for _ in range(5):
        eventos += s.ciclo(ok(A=obs_site("Site A", conectado=False)))
    assert tipos(eventos) == ["SITE_OFFLINE"]
    assert eventos[0].dados["motivo"] == "desconectado_cato"


def test_site_pendente_adia_queda_de_link(cfg, relogio):
    """Link notifica antes do site? Não: o site pendente adia o aviso do link (data-model §3.2)."""
    est = estado_online(A=["W1", "W2"])
    s = Simulador(cfg, relogio, est)
    # W1 cai primeiro; W2 cai 2 ciclos depois => site fica offline (todos inativos) depois.
    eventos = []
    eventos += s.ciclo(ok(A=obs_site("Site A", W1=False, W2=True)))
    eventos += s.ciclo(ok(A=obs_site("Site A", W1=False, W2=True)))
    eventos += s.ciclo(ok(A=obs_site("Site A", W1=False, W2=False)))   # site PENDENTE a partir daqui
    assert eventos == []
    # W1 já tem 120 s; no próximo ciclo (180 s) o link atingiria a tolerância, mas o site está pendente.
    eventos += s.ciclo(ok(A=obs_site("Site A", W1=False, W2=False)))
    assert eventos == []
    assert s.estado.sites["A"].links["W1"].estado == EstadoItem.PENDENTE_OFFLINE
    eventos += s.ciclo(ok(A=obs_site("Site A", W1=False, W2=False)))
    eventos += s.ciclo(ok(A=obs_site("Site A", W1=False, W2=False)))
    assert tipos(eventos) == ["SITE_OFFLINE"]


def test_site_sem_links_monitorados_nao_cai_por_todos_inativos(cfg, relogio):
    s = sim(cfg, relogio, A=[])
    eventos = []
    for _ in range(6):
        eventos += s.ciclo(ok(A=obs_site("Site A")))
    assert eventos == []


def test_link_ausente_com_site_desconectado_nao_incrementa_ausencias(cfg, relogio):
    s = sim(cfg, relogio, A=["W1"])
    for _ in range(5):
        s.ciclo(ok(A=obs_site("Site A", conectado=False)))
    assert s.estado.sites["A"].links["W1"].ausencias == 0
    assert "W1" in s.estado.sites["A"].links


def test_link_ausente_com_site_conectado_e_removido_apos_3_ausencias(cfg, relogio):
    s = sim(cfg, relogio, A=["W1", "W2"])
    for i in range(2):
        s.ciclo(ok(A=obs_site("Site A", W2=True)))
        assert "W1" in s.estado.sites["A"].links
    s.ciclo(ok(A=obs_site("Site A", W2=True)))
    assert "W1" not in s.estado.sites["A"].links


def test_site_ausente_removido_apos_3_ciclos_validos(cfg, relogio):
    s = sim(cfg, relogio, A=["W1"], B=["W1"])
    for _ in range(3):
        s.ciclo(ok(B=obs_site("Site B", W1=True)))
    assert "A" not in s.estado.sites and "B" in s.estado.sites


def test_item_ausente_zera_contador_quando_volta(cfg, relogio):
    s = sim(cfg, relogio, A=["W1"], B=["W1"])
    s.ciclo(ok(B=obs_site("Site B", W1=True)))
    s.ciclo(ok(A=obs_site("Site A", W1=True), B=obs_site("Site B", W1=True)))
    assert s.estado.sites["A"].ausencias == 0


def test_ordem_deterministica_por_site_id(cfg, relogio):
    s = sim(cfg, relogio, B=["W1"], A=["W1"])
    eventos = []
    for _ in range(5):
        eventos += s.ciclo(ok(B=obs_site("Site B", W1=False), A=obs_site("Site A", W1=False)))
    # tudo offline em ambos => SITE_OFFLINE de A antes de B, ids em sequência
    assert [e.dados["site_id"] for e in eventos] == ["A", "B"]
    assert [e.id for e in eventos] == ["evt-000001", "evt-000002"]


def test_item_novo_entra_em_silencio(cfg, relogio):
    s = sim(cfg, relogio, A=["W1"])
    eventos = s.ciclo(ok(A=obs_site("Site A", W1=True, W2=False)))
    assert eventos == []
    assert s.estado.sites["A"].links["W2"].estado == EstadoItem.OFFLINE_NOTIFICADO


def test_estado_original_nao_e_alterado(cfg, relogio):
    from cato_monitor.motor import avaliar_ciclo

    est = estado_online(A=["W1"])
    avaliar_ciclo(est, ok(A=obs_site("Site A", W1=False)), relogio.agora(), cfg)
    assert est.sites["A"].links["W1"].estado == EstadoItem.ONLINE
