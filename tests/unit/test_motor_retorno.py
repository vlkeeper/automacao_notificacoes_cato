from cato_monitor.modelos import EstadoItem, Origem

from ..helpers import Simulador, estado_online, obs_site, ok, tipos


def derrubar_link(s, ciclos=5):
    ev = []
    for _ in range(ciclos):
        ev += s.ciclo(ok(A=obs_site("Site A", W1=False, W2=True)))
    return ev


def test_link_retorno_com_duracao(cfg, relogio):
    s = Simulador(cfg, relogio, estado_online(A=["W1", "W2"]))
    assert tipos(derrubar_link(s)) == ["LINK_OFFLINE"]
    inicio = s.estado.sites["A"].links["W1"].inicio_queda
    relogio.avancar(600)
    ev = s.ciclo(ok(A=obs_site("Site A", W1=True, W2=True)), avancar=0)
    assert tipos(ev) == ["LINK_RETORNO"]
    assert ev[0].dados["retorno_em"] == relogio.agora().isoformat(timespec="seconds")
    assert ev[0].dados["inicio_queda"] == inicio.isoformat(timespec="seconds")
    assert s.estado.sites["A"].links["W1"].estado == EstadoItem.ONLINE


def test_sem_aviso_de_retorno_se_a_queda_nao_foi_notificada(cfg, relogio):
    s = Simulador(cfg, relogio, estado_online(A=["W1", "W2"]))
    ev = s.ciclo(ok(A=obs_site("Site A", W1=False, W2=True)))
    ev += s.ciclo(ok(A=obs_site("Site A", W1=True, W2=True)))
    assert ev == []


def test_site_retorno_e_links_cobertos_voltam_em_silencio(cfg, relogio):
    s = Simulador(cfg, relogio, estado_online(A=["W1", "W2"]))
    for _ in range(5):
        s.ciclo(ok(A=obs_site("Site A", W1=False, W2=False)))
    ev = s.ciclo(ok(A=obs_site("Site A", W1=True, W2=True)))
    assert tipos(ev) == ["SITE_RETORNO"]
    assert ev[0].dados["links_ainda_offline"] == []
    assert all(l.estado == EstadoItem.ONLINE and not l.coberto_pelo_site
               for l in s.estado.sites["A"].links.values())


def test_site_volta_com_link_ainda_fora(cfg, relogio):
    s = Simulador(cfg, relogio, estado_online(A=["W1", "W2"]))
    for _ in range(5):
        s.ciclo(ok(A=obs_site("Site A", W1=False, W2=False)))
    ev = s.ciclo(ok(A=obs_site("Site A", W1=True, W2=False)))
    assert tipos(ev) == ["SITE_RETORNO"]
    ainda = ev[0].dados["links_ainda_offline"]
    assert len(ainda) == 1 and ainda[0][0] == "W2"
    w2 = s.estado.sites["A"].links["W2"]
    assert w2.estado == EstadoItem.OFFLINE_NOTIFICADO and not w2.coberto_pelo_site
    # o link continua como pendência e, ao voltar, tem aviso próprio
    ev = s.ciclo(ok(A=obs_site("Site A", W1=True, W2=True)))
    assert tipos(ev) == ["LINK_RETORNO"]


def test_item_de_linha_de_base_offline_que_volta_gera_retorno(cfg, relogio):
    s = Simulador(cfg, relogio)
    s.ciclo(ok(A=obs_site("Site A", W1=False, W2=True)))  # linha de base
    assert s.estado.sites["A"].links["W1"].origem == Origem.LINHA_BASE
    ev = s.ciclo(ok(A=obs_site("Site A", W1=True, W2=True)))
    assert tipos(ev) == ["LINK_RETORNO"]
