"""Migração do state.json v1 (fila única) para v2 (filas por canal)."""

import json
from datetime import timedelta

import pytest

from cato_monitor import estado_store as store
from cato_monitor.modelos import EstadoMonitor, EventoNotificacao, TipoEvento

from ..conftest import T0


def _v1_com_pendentes() -> dict:
    d = EstadoMonitor().para_dict()
    del d["filas"], d["entrega"]
    d["schema_version"] = 1
    tipos = ["LINK_OFFLINE", "MONITOR_INICIADO", "SITE_RETORNO", "MONITOR_FALHA"]
    d["pendente_envio"] = [
        EventoNotificacao(id=f"evt-{i:06d}", tipo=TipoEvento(t), ocorrido_em=T0, criado_em=T0,
                          dados={}, tentativas=i, ultimo_erro="http_500").para_dict()
        for i, t in enumerate(tipos, 1)
    ]
    return d


def test_migracao_v1_distribui_por_canal_preservando_ordem(tmp_path):
    original = json.dumps(_v1_com_pendentes(), ensure_ascii=False)
    (tmp_path / "state.json").write_text(original, encoding="utf-8")
    est, motivo = store.carregar(tmp_path, T0)
    assert motivo is None
    assert [e.tipo.value for e in est.filas["rede"]] == ["LINK_OFFLINE", "SITE_RETORNO"]
    assert [e.tipo.value for e in est.filas["operacional"]] == ["MONITOR_INICIADO", "MONITOR_FALHA"]
    assert est.filas["rede"][1].tentativas == 3 and est.filas["rede"][1].ultimo_erro == "http_500"
    assert est.entrega["rede"].falha_desde is None and not est.entrega["operacional"].aviso_emitido
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))["schema_version"] == 2
    copias = list(tmp_path.glob("state.json.v1-*"))
    assert len(copias) == 1 and copias[0].read_text(encoding="utf-8") == original


def test_migracao_nao_se_repete(tmp_path):
    (tmp_path / "state.json").write_text(json.dumps(_v1_com_pendentes()), encoding="utf-8")
    store.carregar(tmp_path, T0)
    est, _ = store.carregar(tmp_path, T0 + timedelta(hours=1))
    assert len(list(tmp_path.glob("state.json.v1-*"))) == 1
    assert len(est.filas["rede"]) == 2


def test_migracao_v1_vazio(tmp_path):
    d = _v1_com_pendentes()
    d["pendente_envio"] = []
    (tmp_path / "state.json").write_text(json.dumps(d), encoding="utf-8")
    est, motivo = store.carregar(tmp_path, T0)
    assert motivo is None and est.filas == {"rede": [], "operacional": []}


def test_v1_com_tipo_desconhecido_vira_linha_de_base(tmp_path):
    d = _v1_com_pendentes()
    d["pendente_envio"][0]["tipo"] = "OUTRO"
    (tmp_path / "state.json").write_text(json.dumps(d), encoding="utf-8")
    est, motivo = store.carregar(tmp_path, T0)
    assert motivo is not None and est.sites == {}
    assert list(tmp_path.glob("state.json.corrompido-*"))


def test_v1_corrompido_vira_linha_de_base(tmp_path):
    (tmp_path / "state.json").write_text('{"schema_version": 1, "sites": ', encoding="utf-8")
    _, motivo = store.carregar(tmp_path, T0)
    assert motivo is not None and list(tmp_path.glob("state.json.corrompido-*"))


def test_schema_3_encerra(tmp_path):
    d = EstadoMonitor().para_dict()
    d["schema_version"] = 3
    (tmp_path / "state.json").write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        store.carregar(tmp_path, T0)
    assert exc.value.code == 1


def test_falha_na_copia_nao_impede_migracao(tmp_path, monkeypatch):
    (tmp_path / "state.json").write_text(json.dumps(_v1_com_pendentes()), encoding="utf-8")

    def quebra(*a, **k):
        raise OSError("somente leitura")

    monkeypatch.setattr(store.shutil, "copy2", quebra)
    est, motivo = store.carregar(tmp_path, T0)
    assert motivo is None and len(est.filas["rede"]) == 2 and len(est.filas["operacional"]) == 2
