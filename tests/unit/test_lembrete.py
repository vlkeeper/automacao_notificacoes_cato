from datetime import datetime, timedelta, timezone

from cato_monitor.modelos import ConsultaFalhou, EstadoItem, EstadoMonitor, MAX_PENDENCIAS_POR_CARD

from ..conftest import RelogioFake
from ..helpers import Simulador, estado_online, obs_site, ok, tipos

# 06/10/2026 08:00 em Brasília (UTC-3) = 11:00 UTC
OITO = datetime(2026, 10, 6, 11, 0, 0, tzinfo=timezone.utc)


def estado_com_pendencia():
    """Link W1 já notificado como offline."""
    est = estado_online(A=["W1", "W2"])
    link = est.sites["A"].links["W1"]
    link.estado, link.notificado = EstadoItem.OFFLINE_NOTIFICADO, True
    link.inicio_queda = OITO - timedelta(hours=10)
    est.monitor.ultimo_lembrete_data = "2026-10-05"
    return est


def obs():
    return ok(A=obs_site("Site A", W1=False, W2=True))


def test_com_pendencias_gera_um_lembrete(cfg):
    rel = RelogioFake(OITO - timedelta(seconds=120))
    s = Simulador(cfg, rel, estado_com_pendencia())
    assert s.ciclo(obs(), avancar=0) == []  # 07:58
    ev = s.ciclo(obs(), avancar=120)        # 08:00
    assert tipos(ev) == ["LEMBRETE_DIARIO"]
    assert ev[0].dados["pendencias"] == [
        {"site_nome": "Site A", "link_nome": "W1", "tipo": "WAN",
         "inicio_queda": "2026-10-06T01:00:00+00:00"}
    ]
    assert s.estado.monitor.ultimo_lembrete_data == "2026-10-06"
    assert s.ciclo(obs()) == []  # não repete no mesmo dia


def test_sem_pendencias_nao_gera_mas_marca_a_data(cfg):
    s = Simulador(cfg, RelogioFake(OITO), estado_online(A=["W1"]))
    s.estado.monitor.ultimo_lembrete_data = "2026-10-05"
    assert s.ciclo(ok(A=obs_site("Site A", W1=True)), avancar=0) == []
    assert s.estado.monitor.ultimo_lembrete_data == "2026-10-06"


def test_apos_reinicio_nao_duplica(cfg):
    s = Simulador(cfg, RelogioFake(OITO), estado_com_pendencia())
    assert tipos(s.ciclo(obs(), avancar=0)) == ["LEMBRETE_DIARIO"]
    recarregado = EstadoMonitor.de_dict(s.estado.para_dict())
    s2 = Simulador(cfg, RelogioFake(OITO + timedelta(minutes=5)), recarregado)
    assert s2.ciclo(obs(), avancar=0) == []


def test_monitor_parado_as_oito_envia_no_primeiro_ciclo_bom(cfg):
    s = Simulador(cfg, RelogioFake(OITO + timedelta(hours=2)), estado_com_pendencia())
    assert tipos(s.ciclo(obs(), avancar=0)) == ["LEMBRETE_DIARIO"]


def test_virada_de_dia_em_brasilia(cfg):
    # 02:30 UTC de 07/10 ainda é 06/10 23:30 em Brasília; 11:00 UTC de 07/10 já é o novo dia
    est = estado_com_pendencia()
    est.monitor.ultimo_lembrete_data = "2026-10-06"
    rel = RelogioFake(datetime(2026, 10, 7, 2, 30, tzinfo=timezone.utc))
    s = Simulador(cfg, rel, est)
    assert s.ciclo(obs(), avancar=0) == []
    rel._agora = datetime(2026, 10, 7, 11, 0, tzinfo=timezone.utc)
    assert tipos(s.ciclo(obs(), avancar=0)) == ["LEMBRETE_DIARIO"]
    assert s.estado.monitor.ultimo_lembrete_data == "2026-10-07"


def test_antes_do_horario_nada(cfg):
    s = Simulador(cfg, RelogioFake(OITO - timedelta(hours=1)), estado_com_pendencia())
    assert s.ciclo(obs(), avancar=0) == []
    assert s.estado.monitor.ultimo_lembrete_data == "2026-10-05"


def test_consulta_falha_nao_avalia_lembrete(cfg):
    s = Simulador(cfg, RelogioFake(OITO), estado_com_pendencia())
    assert s.ciclo(ConsultaFalhou("timeout"), avancar=0) == []
    assert s.estado.monitor.ultimo_lembrete_data == "2026-10-05"
    assert tipos(s.ciclo(obs())) == ["LEMBRETE_DIARIO"]


def test_item_removido_sai_da_lista(cfg):
    s = Simulador(cfg, RelogioFake(OITO), estado_com_pendencia())
    s.estado.monitor.ultimo_lembrete_data = "2026-10-06"  # lembrete de hoje já avaliado
    for _ in range(3):  # W1 some do inventário por 3 ciclos válidos
        s.ciclo(ok(A=obs_site("Site A", W2=True)), avancar=0)
    assert "W1" not in s.estado.sites["A"].links


def test_item_de_linha_de_base_entra_no_lembrete(cfg):
    s = Simulador(cfg, RelogioFake(OITO - timedelta(hours=1)))
    s.ciclo(obs(), avancar=0)  # linha de base 07:00: W1 já offline
    ev = s.ciclo(obs(), avancar=3600)  # 08:00
    assert tipos(ev) == ["LEMBRETE_DIARIO"]
    assert ev[0].dados["pendencias"][0]["link_nome"] == "W1"


def test_links_cobertos_pelo_site_nao_repetem_no_lembrete(cfg):
    s = Simulador(cfg, RelogioFake(OITO - timedelta(hours=1)), estado_online(A=["W1", "W2"]))
    caido = lambda: ok(A=obs_site("Site A", W1=False, W2=False))
    for _ in range(5):
        s.ciclo(caido())
    ev = s.ciclo(caido(), avancar=3600)
    assert tipos(ev) == ["LEMBRETE_DIARIO"]
    assert [p["link_nome"] for p in ev[0].dados["pendencias"]] == [None]  # só o site


def test_divide_em_partes_quando_ha_muitas_pendencias(cfg):
    n = MAX_PENDENCIAS_POR_CARD * 2 + 5
    est = estado_online(**{f"S{i:03d}": ["W1"] for i in range(n)})
    for site in est.sites.values():
        l = site.links["W1"]
        l.estado, l.notificado, l.inicio_queda = EstadoItem.OFFLINE_NOTIFICADO, True, OITO - timedelta(hours=1)
    est.monitor.ultimo_lembrete_data = "2026-10-05"
    s = Simulador(cfg, RelogioFake(OITO), est)
    resultado = ok(**{f"S{i:03d}": obs_site(f"Site S{i:03d}", W1=False) for i in range(n)})
    ev = s.ciclo(resultado, avancar=0)
    assert tipos(ev) == ["LEMBRETE_DIARIO"] * 3
    assert [(e.dados["parte"], e.dados["total_partes"]) for e in ev] == [(1, 3), (2, 3), (3, 3)]
    assert sum(len(e.dados["pendencias"]) for e in ev) == n
