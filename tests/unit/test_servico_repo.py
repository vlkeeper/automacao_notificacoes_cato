"""Unidades Quadlet do monitor e Containerfile (feature 005): o que o contrato exige, sem rodar Podman."""

import re
from pathlib import Path

import pytest

from tests.unit.test_segredos_repo import PALAVRAS_SECRETAS

RAIZ = Path(__file__).parents[2]
DEPLOY = RAIZ / "deploy"


def _ler_ini(caminho: Path) -> dict[str, list[tuple[str, str]]]:
    """Parse simples de INI do systemd: seções com chaves possivelmente repetidas."""
    secoes: dict[str, list[tuple[str, str]]] = {}
    atual = None
    for bruta in caminho.read_text(encoding="utf-8").splitlines():
        linha = bruta.strip()
        if not linha or linha.startswith(("#", ";")):
            continue
        if linha.startswith("[") and linha.endswith("]"):
            atual = linha[1:-1]
            secoes.setdefault(atual, [])
        elif "=" in linha and atual is not None:
            chave, valor = linha.split("=", 1)
            secoes[atual].append((chave.strip(), valor.strip()))
    return secoes


def _valores(ini, secao: str, chave: str) -> list[str]:
    return [v for k, v in ini.get(secao, []) if k == chave]


def _um(ini, secao: str, chave: str) -> str:
    valores = _valores(ini, secao, chave)
    assert len(valores) == 1, f"[{secao}] {chave}: esperado 1 valor, achei {valores}"
    return valores[0]


@pytest.fixture(scope="module")
def container():
    return _ler_ini(DEPLOY / "cato-monitor.container")


@pytest.fixture(scope="module")
def volume():
    return _ler_ini(DEPLOY / "cato-monitor.volume")


@pytest.fixture(scope="module")
def containerfile() -> str:
    return (RAIZ / "Containerfile").read_text(encoding="utf-8")


def test_arquivos_existem_e_sem_publicacao_de_porta(container, volume):
    assert "Container" in container and "Volume" in volume
    assert not _valores(container, "Container", "PublishPort")


def test_parada_e_init(container):
    assert _um(container, "Container", "StopTimeout") == "30"
    assert _um(container, "Container", "RunInit") == "true"
    assert int(_um(container, "Service", "TimeoutStopSec")) > 30


def test_saude_igual_ao_healthcheck_da_imagem(container, containerfile):
    hc = re.search(r"HEALTHCHECK\s+(.*?)\n\s*CMD\s+(.+)", containerfile)
    assert hc, "HEALTHCHECK ausente do Containerfile"
    opcoes = dict(re.findall(r"--(\w[\w-]*)=(\S+)", hc.group(1)))
    assert _um(container, "Container", "HealthCmd") == hc.group(2).strip()
    assert _um(container, "Container", "HealthInterval") == opcoes["interval"]
    assert _um(container, "Container", "HealthTimeout") == opcoes["timeout"]
    assert _um(container, "Container", "HealthStartPeriod") == opcoes["start-period"]
    assert _um(container, "Container", "HealthRetries") == opcoes["retries"]
    assert _um(container, "Container", "HealthOnFailure") == "none"


def test_log_driver_definido(container):
    assert _um(container, "Container", "LogDriver") in {"journald", "passthrough"}


def test_recuperacao_sem_limite(container):
    assert _um(container, "Service", "Restart") == "always"
    assert _um(container, "Service", "RestartSec") == "30"
    assert _um(container, "Unit", "StartLimitIntervalSec") == "0"
    assert _um(container, "Install", "WantedBy") == "multi-user.target"
    assert _um(container, "Unit", "After") == "network-online.target"
    assert _um(container, "Unit", "Wants") == "network-online.target"


def test_volume_e_estado(container, volume):
    assert _um(volume, "Volume", "VolumeName") == "cato-monitor-data"
    assert _um(volume, "Volume", "User") == "10001"
    assert _um(volume, "Volume", "Group") == "10001"
    assert _um(container, "Container", "Volume") == "cato-monitor.volume:/data"
    assert "STATE_DIR=/data" in _valores(container, "Container", "Environment")


def test_hardening(container):
    assert _um(container, "Container", "ReadOnly") == "true"
    assert _um(container, "Container", "Tmpfs") == "/tmp"
    assert _um(container, "Container", "DropCapability") == "ALL"
    assert _um(container, "Container", "NoNewPrivileges") == "true"
    # UID numérico (a resolução do nome "monitor" falha no healthcheck/exec do Podman 5.7); nunca root
    assert _um(container, "Container", "User") == "10001"
    assert not _valores(container, "Container", "PublishPort")


def test_instancia_unica_por_nome_fixo(container):
    assert _um(container, "Container", "ContainerName") == "cato-monitor"
    assert not _valores(container, "Container", "Scale")


def test_segredos_somente_por_arquivo_de_ambiente(container):
    assert _um(container, "Container", "EnvironmentFile") == "/etc/cato-monitor/.env"
    for valor in _valores(container, "Container", "Environment"):
        assert not PALAVRAS_SECRETAS.search(valor), f"segredo em Environment=: {valor}"


def test_imagem_local_sem_pull(container):
    assert _um(container, "Container", "Image") == "localhost/cato-monitor:latest"
    assert _um(container, "Container", "Pull") == "never"


def test_containerfile_base_fixada_e_dependencias_com_hash(containerfile):
    assert re.search(r"^ARG PYTHON_IMAGE=\S+@sha256:[0-9a-f]{64}", containerfile, re.M)
    assert "--require-hashes" in containerfile


def test_containerfile_usuario_volume_e_entrypoint(containerfile):
    assert re.search(r"useradd .*--uid 10001", containerfile)
    assert re.search(r"^USER monitor$", containerfile, re.M)
    assert re.search(r"^VOLUME /data$", containerfile, re.M)
    assert re.search(r"^WORKDIR /app$", containerfile, re.M)
    assert 'ENTRYPOINT ["python", "-m", "cato_monitor"]' in containerfile
    assert "HEALTHCHECK" in containerfile
