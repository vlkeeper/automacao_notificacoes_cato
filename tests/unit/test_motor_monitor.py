from cato_monitor.modelos import ConsultaFalhou, EstadoItem, EstadoMonitor, Origem

from ..helpers import Simulador, estado_online, obs_site, ok, tipos


def falha(motivo="timeout"):
    return ConsultaFalhou(motivo)


def test_quatro_falhas_nada_quinta_gera_aviso_depois_nada(cfg, relogio):
    s = Simulador(cfg, relogio, estado_online(A=["W1"]))
    for _ in range(4):
        assert s.ciclo(falha()) == []
    ev = s.ciclo(falha("http_500"))
    assert tipos(ev) == ["MONITOR_FALHA"]
    assert ev[0].dados["falhas_consecutivas"] == 5 and ev[0].dados["ultimo_motivo"] == "http_500"
    assert "desde" in ev[0].dados
    for _ in range(3):
        assert s.ciclo(falha()) == []  # 1x por sequência


def test_sucesso_apos_alerta_gera_recuperado_e_zera(cfg, relogio):
    s = Simulador(cfg, relogio, estado_online(A=["W1"]))
    for _ in range(6):
        s.ciclo(falha())
    ev = s.ciclo(ok(A=obs_site("Site A", W1=True)))
    assert tipos(ev) == ["MONITOR_RECUPERADO"]
    assert ev[0].dados["falhas_total"] == 6
    m = s.estado.monitor
    assert m.falhas_consecutivas == 0 and not m.alerta_falha_enviado
    assert s.ciclo(ok(A=obs_site("Site A", W1=True))) == []


def test_sucesso_sem_alerta_previo_nao_gera_recuperado(cfg, relogio):
    s = Simulador(cfg, relogio, estado_online(A=["W1"]))
    for _ in range(3):
        s.ciclo(falha())
    assert s.ciclo(ok(A=obs_site("Site A", W1=True))) == []
    assert s.estado.monitor.falhas_consecutivas == 0


def test_falha_nunca_muda_itens(cfg, relogio):
    s = Simulador(cfg, relogio, estado_online(A=["W1"]))
    s.ciclo(ok(A=obs_site("Site A", W1=False)))  # PENDENTE
    antes = s.estado.sites["A"].para_dict()
    for _ in range(10):
        s.ciclo(falha())
    assert s.estado.sites["A"].para_dict() == antes


def test_contador_persistido_entre_reinicios(cfg, relogio):
    s = Simulador(cfg, relogio, estado_online(A=["W1"]))
    for _ in range(3):
        s.ciclo(falha())
    s2 = Simulador(cfg, relogio, EstadoMonitor.de_dict(s.estado.para_dict()))
    assert s2.ciclo(falha()) == []
    assert tipos(s2.ciclo(falha())) == ["MONITOR_FALHA"]


def test_linha_de_base(cfg, relogio):
    s = Simulador(cfg, relogio)  # estado vazio
    ev = s.ciclo(ok(A=obs_site("Site A", W1=True, W2=False), B=obs_site("Site B", conectado=False)))
    assert tipos(ev) == ["MONITOR_INICIADO"]
    d = ev[0].dados
    assert d["sites_total"] == 2 and d["links_total"] == 2
    offline = {(i["site_nome"], i["link_nome"]) for i in d["itens_offline"]}
    assert offline == {("Site A", "W2"), ("Site B", None)}
    a = s.estado.sites["A"]
    assert a.links["W1"].estado == EstadoItem.ONLINE
    w2 = a.links["W2"]
    assert w2.estado == EstadoItem.OFFLINE_NOTIFICADO and w2.origem == Origem.LINHA_BASE and w2.notificado
    assert s.estado.sites["B"].estado == EstadoItem.OFFLINE_NOTIFICADO
    # ciclo seguinte: nenhum aviso de queda
    assert s.ciclo(ok(A=obs_site("Site A", W1=True, W2=False), B=obs_site("Site B", conectado=False))) == []


def test_linha_de_base_apos_o_horario_marca_lembrete_de_hoje(cfg, relogio):
    relogio.avancar(2 * 3600)  # 12:00 UTC = 09:00 local
    s = Simulador(cfg, relogio)
    s.ciclo(ok(A=obs_site("Site A", W1=False)), avancar=0)
    assert s.estado.monitor.ultimo_lembrete_data == "2026-10-06"


def test_snapshot_vazio_com_estado_vazio_nao_gera_linha_de_base(cfg, relogio):
    s = Simulador(cfg, relogio)
    assert s.ciclo(ok()) == []
    assert s.ciclo(ok()) == []
