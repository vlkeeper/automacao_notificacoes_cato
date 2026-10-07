import json
import os
from datetime import timedelta
from pathlib import Path

import pytest

from cato_monitor import estado_store as store
from cato_monitor.modelos import (
    EstadoItem,
    EstadoMonitor,
    EventoNotificacao,
    Link,
    Origem,
    Site,
    TipoEvento,
    verificar_invariantes,
)

from ..conftest import T0


def _estado_exemplo() -> EstadoMonitor:
    est = EstadoMonitor()
    est.sites["1001"] = Site(
        nome="Filial Campinas",
        links={
            "s-77/WAN1": Link(nome="WAN1 - Operadora A", tipo="WAN", socket="primário"),
            "s-77/WAN2": Link(
                nome="WAN2 - Operadora B", tipo="WAN", socket="primário",
                estado=EstadoItem.OFFLINE_NOTIFICADO, inicio_queda=T0 - timedelta(hours=2),
                notificado=True, origem=Origem.LINHA_BASE,
            ),
        },
    )
    est.pendente_envio.append(
        EventoNotificacao(id="evt-000001", tipo=TipoEvento.LINK_OFFLINE, ocorrido_em=T0,
                          criado_em=T0, dados={"site_nome": "Filial Campinas"}, tentativas=2,
                          ultimo_erro="http_500")
    )
    est.monitor.proximo_seq = 2
    est.monitor.ultimo_lembrete_data = "2026-10-06"
    return est


def test_ida_e_volta(tmp_path):
    est = _estado_exemplo()
    store.salvar(est, tmp_path, T0)
    lido, motivo = store.carregar(tmp_path, T0)
    assert motivo is None
    assert lido.para_dict() == est.para_dict()
    assert lido.sites["1001"].links["s-77/WAN2"].inicio_queda == T0 - timedelta(hours=2)


def test_arquivo_ausente_e_linha_de_base(tmp_path):
    est, motivo = store.carregar(tmp_path, T0)
    assert motivo == "arquivo_ausente"
    assert est.sites == {}


def test_falha_entre_tmp_e_replace_mantem_arquivo_anterior(tmp_path, monkeypatch):
    est = _estado_exemplo()
    store.salvar(est, tmp_path, T0)
    original = (tmp_path / "state.json").read_text(encoding="utf-8")

    est.monitor.falhas_consecutivas = 4

    def quebra(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", quebra)
    with pytest.raises(OSError):
        store.salvar(est, tmp_path, T0 + timedelta(seconds=60))
    monkeypatch.undo()

    assert (tmp_path / "state.json").read_text(encoding="utf-8") == original
    lido, motivo = store.carregar(tmp_path, T0)
    assert motivo is None
    assert lido.monitor.falhas_consecutivas == 0


def test_corrompido_gera_estado_vazio_e_preserva_arquivo(tmp_path):
    (tmp_path / "state.json").write_text("{ isto não é json", encoding="utf-8")
    est, motivo = store.carregar(tmp_path, T0)
    assert est.sites == {} and motivo.startswith("estado_invalido")
    assert not (tmp_path / "state.json").exists()
    assert len(list(tmp_path.glob("state.json.corrompido-*"))) == 1


def test_schema_version_ausente_vira_linha_de_base(tmp_path):
    (tmp_path / "state.json").write_text(json.dumps({"sites": {}}), encoding="utf-8")
    est, motivo = store.carregar(tmp_path, T0)
    assert motivo is not None and est.sites == {}
    assert list(tmp_path.glob("state.json.corrompido-*"))


def test_invariante_violada_vira_linha_de_base(tmp_path):
    est = _estado_exemplo()
    est.sites["1001"].links["s-77/WAN1"].notificado = True  # ONLINE com notificado
    assert verificar_invariantes(est)
    store.salvar(est, tmp_path, T0)
    lido, motivo = store.carregar(tmp_path, T0)
    assert motivo is not None and lido.sites == {}


def test_schema_version_futuro_encerra_com_exit_1(tmp_path):
    dados = _estado_exemplo().para_dict()
    dados["schema_version"] = 99
    (tmp_path / "state.json").write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        store.carregar(tmp_path, T0)
    assert exc.value.code == 1
    assert (tmp_path / "state.json").exists()  # não sobrescreve nem move


def test_segundo_lock_encerra_com_exit_1(tmp_path):
    primeiro = store.LockInstancia(tmp_path)
    primeiro.adquirir()
    try:
        with pytest.raises(SystemExit) as exc:
            store.LockInstancia(tmp_path).adquirir()
        assert exc.value.code == 1
    finally:
        primeiro.liberar()
    # depois de liberado, outro processo consegue
    outro = store.LockInstancia(tmp_path)
    outro.adquirir()
    outro.liberar()


def test_last_cycle_atomico(tmp_path):
    store.gravar_last_cycle(tmp_path, T0)
    assert (tmp_path / "last_cycle").read_text().strip() == "2026-10-06T10:00:00+00:00"
    assert not list(tmp_path.glob("*.tmp"))


def test_json_valido_contra_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).parents[2] / "specs/001-cato-socket/contracts/state-file.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    store.salvar(_estado_exemplo(), tmp_path, T0)
    dados = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    jsonschema.validate(dados, schema)
