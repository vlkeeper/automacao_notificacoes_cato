from datetime import timedelta

from cato_monitor.modelos import EstadoItem, Link
from cato_monitor.transicoes import TipoAcao, proximo_estado

from ..conftest import T0

TOL = timedelta(seconds=180)


def link(estado=EstadoItem.ONLINE, inicio=None, notificado=False, coberto=False):
    return Link(nome="WAN1", tipo="WAN", estado=estado, inicio_queda=inicio, notificado=notificado,
                coberto_pelo_site=coberto)


def test_online_x_online():
    novo, acoes = proximo_estado(link(), False, T0, TOL)
    assert novo.estado == EstadoItem.ONLINE and acoes == []


def test_online_x_offline_vira_pendente():
    novo, acoes = proximo_estado(link(), True, T0, TOL)
    assert novo.estado == EstadoItem.PENDENTE_OFFLINE
    assert novo.inicio_queda == T0 and acoes == []


def test_pendente_x_offline_dentro_da_tolerancia():
    item = link(EstadoItem.PENDENTE_OFFLINE, T0)
    novo, acoes = proximo_estado(item, True, T0 + timedelta(seconds=179), TOL)
    assert novo.estado == EstadoItem.PENDENTE_OFFLINE and acoes == []


def test_pendente_x_offline_na_tolerancia_exata_notifica():
    item = link(EstadoItem.PENDENTE_OFFLINE, T0)
    novo, acoes = proximo_estado(item, True, T0 + TOL, TOL)
    assert novo.estado == EstadoItem.OFFLINE_NOTIFICADO and novo.notificado
    assert novo.inicio_queda == T0
    assert [a.tipo for a in acoes] == [TipoAcao.QUEDA]


def test_pendente_x_offline_apos_tolerancia_notifica():
    item = link(EstadoItem.PENDENTE_OFFLINE, T0)
    _, acoes = proximo_estado(item, True, T0 + TOL + timedelta(seconds=60), TOL)
    assert [a.tipo for a in acoes] == [TipoAcao.QUEDA]


def test_pendente_x_online_volta_em_silencio_e_limpa():
    item = link(EstadoItem.PENDENTE_OFFLINE, T0)
    novo, acoes = proximo_estado(item, False, T0 + timedelta(seconds=60), TOL)
    assert novo.estado == EstadoItem.ONLINE
    assert novo.inicio_queda is None and not novo.notificado and acoes == []


def test_notificado_x_offline_nao_repete():
    item = link(EstadoItem.OFFLINE_NOTIFICADO, T0, True)
    novo, acoes = proximo_estado(item, True, T0 + timedelta(hours=3), TOL)
    assert novo == item and acoes == []


def test_notificado_x_online_retorno_com_duracao_e_limpa():
    item = link(EstadoItem.OFFLINE_NOTIFICADO, T0, True, coberto=True)
    novo, acoes = proximo_estado(item, False, T0 + timedelta(minutes=12), TOL)
    assert novo.estado == EstadoItem.ONLINE
    assert novo.inicio_queda is None and not novo.notificado and not novo.coberto_pelo_site
    assert acoes[0].tipo == TipoAcao.RETORNO and acoes[0].duracao == timedelta(minutes=12)


def test_observacao_none_deixa_inalterado():
    for estado, inicio in [(EstadoItem.ONLINE, None), (EstadoItem.PENDENTE_OFFLINE, T0),
                           (EstadoItem.OFFLINE_NOTIFICADO, T0)]:
        item = link(estado, inicio, estado == EstadoItem.OFFLINE_NOTIFICADO)
        novo, acoes = proximo_estado(item, None, T0 + timedelta(hours=1), TOL)
        assert novo == item and acoes == []


def test_funcao_nao_altera_o_item_original():
    item = link()
    proximo_estado(item, True, T0, TOL)
    assert item.estado == EstadoItem.ONLINE
