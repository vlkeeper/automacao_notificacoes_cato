from datetime import timedelta

import pytest

from cato_monitor.canais import Canal, avaliar_entrega, canal_do_evento
from cato_monitor.modelos import EstadoMonitor, EventoNotificacao, TipoEvento

from ..conftest import T0

ESPERADO = {
    "LINK_OFFLINE": Canal.REDE, "SITE_OFFLINE": Canal.REDE, "LINK_RETORNO": Canal.REDE,
    "SITE_RETORNO": Canal.REDE, "SOCKET_OFFLINE": Canal.REDE, "SOCKET_RETORNO": Canal.REDE, "LEMBRETE_DIARIO": Canal.REDE,
    "MONITOR_FALHA": Canal.OPERACIONAL, "MONITOR_RECUPERADO": Canal.OPERACIONAL,
    "MONITOR_INICIADO": Canal.OPERACIONAL,
}


def ev(tipo, **dados):
    return EventoNotificacao(id="evt-000001", tipo=tipo, ocorrido_em=T0, criado_em=T0, dados=dados)


@pytest.mark.parametrize("tipo", [t for t in TipoEvento if not t.value.startswith("CANAL_")])
def test_todo_tipo_tem_canal(tipo):
    assert canal_do_evento(ev(tipo)) is ESPERADO[tipo.value]


@pytest.mark.parametrize("tipo", [TipoEvento.CANAL_SEM_ENTREGA, TipoEvento.CANAL_NORMALIZADO])
def test_aviso_de_canal_vai_para_o_outro(tipo):
    assert canal_do_evento(ev(tipo, canal_afetado="rede")) is Canal.OPERACIONAL
    assert canal_do_evento(ev(tipo, canal_afetado="operacional")) is Canal.REDE


def test_outro():
    assert Canal.REDE.outro is Canal.OPERACIONAL and Canal.OPERACIONAL.outro is Canal.REDE


FALHA = {Canal.OPERACIONAL: (0, True)}


def _estado_com_fila(n=2):
    est = EstadoMonitor()
    est.filas["operacional"] = [ev(TipoEvento.MONITOR_INICIADO) for _ in range(n)]
    return est


def test_primeira_falha_so_marca_inicio():
    est = _estado_com_fila()
    assert avaliar_entrega(est, FALHA, T0) == []
    assert est.entrega["operacional"].falha_desde == T0 and not est.entrega["operacional"].aviso_emitido


def test_menos_de_15_min_nao_emite():
    est = _estado_com_fila()
    avaliar_entrega(est, FALHA, T0)
    assert avaliar_entrega(est, FALHA, T0 + timedelta(seconds=899)) == []


def test_15_min_emite_uma_vez_no_outro_canal():
    est = _estado_com_fila(3)
    avaliar_entrega(est, FALHA, T0)
    novos = avaliar_entrega(est, FALHA, T0 + timedelta(seconds=900))
    assert len(novos) == 1 and novos[0].tipo is TipoEvento.CANAL_SEM_ENTREGA
    assert novos[0].dados == {"canal_afetado": "operacional", "desde": "2026-10-06T10:00:00+00:00",
                              "pendentes": 3}
    assert canal_do_evento(novos[0]) is Canal.REDE
    assert est.entrega["operacional"].aviso_emitido
    assert avaliar_entrega(est, FALHA, T0 + timedelta(seconds=1200)) == []


def test_entrega_ok_apos_aviso_emite_normalizacao_e_zera():
    est = _estado_com_fila()
    avaliar_entrega(est, FALHA, T0)
    avaliar_entrega(est, FALHA, T0 + timedelta(seconds=900))
    novos = avaliar_entrega(est, {Canal.OPERACIONAL: (2, False)}, T0 + timedelta(seconds=1000))
    assert [n.tipo for n in novos] == [TipoEvento.CANAL_NORMALIZADO]
    assert novos[0].dados["duracao_s"] == 1000 and novos[0].dados["canal_afetado"] == "operacional"
    sit = est.entrega["operacional"]
    assert sit.falha_desde is None and not sit.aviso_emitido


def test_entrega_ok_sem_aviso_so_zera():
    est = _estado_com_fila()
    avaliar_entrega(est, FALHA, T0)
    assert avaliar_entrega(est, {Canal.OPERACIONAL: (1, False)}, T0 + timedelta(seconds=60)) == []
    assert est.entrega["operacional"].falha_desde is None


def test_oscilacao_recomeca_a_contagem():
    est = _estado_com_fila()
    avaliar_entrega(est, FALHA, T0)
    avaliar_entrega(est, {Canal.OPERACIONAL: (1, False)}, T0 + timedelta(seconds=600))
    avaliar_entrega(est, FALHA, T0 + timedelta(seconds=660))
    assert avaliar_entrega(est, FALHA, T0 + timedelta(seconds=1000)) == []  # só 340 s


def test_fila_vazia_sem_tentativa_nao_altera():
    est = _estado_com_fila()
    avaliar_entrega(est, FALHA, T0)
    avaliar_entrega(est, {Canal.OPERACIONAL: (0, False)}, T0 + timedelta(seconds=60))
    assert est.entrega["operacional"].falha_desde == T0


def test_dois_canais_em_falha_geram_um_aviso_para_cada():
    est = _estado_com_fila()
    est.filas["rede"] = [ev(TipoEvento.LINK_OFFLINE)]
    ambos = {Canal.REDE: (0, True), Canal.OPERACIONAL: (0, True)}
    avaliar_entrega(est, ambos, T0)
    novos = avaliar_entrega(est, ambos, T0 + timedelta(seconds=900))
    assert sorted(canal_do_evento(n).value for n in novos) == ["operacional", "rede"]
    assert len({n.id for n in novos}) == 2
