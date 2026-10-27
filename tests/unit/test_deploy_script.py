"""deploy/cato-deploy.sh com git real em repositório temporário e podman/systemctl/curl falsos."""

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

RAIZ = Path(__file__).parents[2]
SCRIPT = RAIZ / "deploy" / "cato-deploy.sh"
WEBHOOK = "https://hooks.exemplo.test/segredo-do-webhook-123"

pytestmark = pytest.mark.skipif(
    not all(shutil.which(b) for b in ("bash", "flock", "git", "jq")),
    reason="precisa de bash, flock, git e jq (Linux)",
)

# Binário falso: registra a chamada; falha se FALHA_<NOME> ou FALHA_<NOME>_<ARG1> estiver definida.
FALSO = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    nome="$(basename "$0")"
    printf '%s\\n' "$nome $*" >> "$FAKE_LOG"
    if [ "$nome" = curl ]; then
        cat > "$FAKE_STDIN_CURL"
        for a in "$@"; do case "$a" in '{'*) printf '%s' "$a" > "$FAKE_CORPO";; esac; done
    fi
    base="FALHA_$(printf '%s' "$nome" | tr a-z A-Z)"
    arg="${base}_$(printf '%s' "${1:-}" | tr a-z A-Z | tr -c A-Z0-9 _)"
    if [ -n "${!base:-}" ] || [ -n "${!arg:-}" ]; then
        echo "erro simulado em $nome $1 https://usuario:senha@gitlab.test/x" >&2
        exit 1
    fi
    if [ "$nome" = systemctl ] && [ "${1:-}" = is-active ] && [ -n "${PARADO:-}" ]; then
        exit 3
    fi
    exit 0
    """
)


def git(*args, cwd):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )


class Ambiente:
    def __init__(self, base: Path):
        self.base = base
        self.origem = base / "origem"
        self.config = base / "etc"
        self.estado = base / "estado"
        self.clone = base / "clone"
        self.bin = base / "bin"
        self.log = base / "chamadas.log"
        self.corpo = base / "corpo.json"
        self.stdin_curl = base / "curl-stdin.txt"
        for d in (self.origem, self.config, self.bin):
            d.mkdir()
        git("init", "-q", "-b", "main", cwd=self.origem)
        self.commit("primeiro commit")
        (self.config / "repo.conf").write_text(f"REPO_URL={self.origem}\nBRANCH=main\n")
        self.webhook(WEBHOOK)
        for nome in ("podman", "systemctl", "curl"):
            f = self.bin / nome
            f.write_text(FALSO)
            f.chmod(0o755)
        self.log.touch()

    def webhook(self, url):
        (self.config / ".env").write_text(
            "CATO_API_KEY=outro-segredo\n"
            + (f"TEAMS_WEBHOOK_OPERACIONAL_URL={url}\n" if url else "")
        )

    def commit(self, titulo):
        (self.origem / "arquivo.txt").write_text(titulo)
        git("add", "-A", cwd=self.origem)
        git("commit", "-q", "-m", titulo, cwd=self.origem)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.origem, capture_output=True, text=True, check=True
        ).stdout.strip()

    def rodar(self, **extra):
        env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "CATO_CONFIG_DIR": str(self.config),
            "CATO_STATE_DIR": str(self.estado),
            "CATO_REPO_DIR": str(self.clone),
            "CATO_LOCK_FILE": str(self.base / "deploy.lock"),
            "CATO_ESTABILIDADE_S": "0",
            "FAKE_LOG": str(self.log),
            "FAKE_STDIN_CURL": str(self.stdin_curl),
            "FAKE_CORPO": str(self.corpo),
            **extra,
        }
        return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)

    def chamadas(self, prefixo=""):
        return [l for l in self.log.read_text().splitlines() if l.startswith(prefixo)]

    def estado_de(self, nome):
        f = self.estado / nome
        return f.read_text().strip() if f.exists() else None

    def card(self):
        return json.loads(self.corpo.read_text())


@pytest.fixture
def amb(tmp_path):
    return Ambiente(tmp_path)


def _tudo(r):
    return r.stdout + r.stderr


def test_sem_commit_novo_so_atualiza_last_check(amb):
    amb.rodar()
    amb.log.write_text("")
    r = amb.rodar()
    assert r.returncode == 0
    assert amb.estado_de("last-check")
    assert not amb.chamadas("podman build")


def test_sucesso_constroi_marca_reinicia_e_avisa(amb):
    sha = amb.commit("segundo commit")
    r = amb.rodar()
    assert r.returncode == 0, _tudo(r)
    build = amb.chamadas("podman build")
    assert len(build) == 1
    assert f"org.opencontainers.image.revision={sha}" in build[0]
    assert "--format docker" in build[0]
    assert f"localhost/cato-monitor:{sha[:12]}" in build[0]
    chamadas = amb.chamadas()
    i_build = next(i for i, l in enumerate(chamadas) if l.startswith("podman build"))
    i_tag = next(i for i, l in enumerate(chamadas) if l.startswith("podman tag"))
    assert i_build < i_tag and "localhost/cato-monitor:latest" in chamadas[i_tag]
    assert amb.chamadas("systemctl try-restart cato-monitor.service")
    assert amb.estado_de("deployed-commit") == sha
    assert amb.estado_de("last-deploy")
    assert amb.estado_de("failed-commit") is None
    assert len(amb.chamadas("curl")) == 1
    card = amb.card()
    assert card["type"] == "message"
    conteudo = card["attachments"][0]["content"]
    assert conteudo["type"] == "AdaptiveCard"
    texto = json.dumps(conteudo, ensure_ascii=False)
    assert "DEPLOY CONCLUÍDO" in texto and "segundo commit" in texto


def test_falha_de_build_nao_move_latest_e_avisa_uma_vez(amb):
    sha = amb.commit("quebra o build")
    r = amb.rodar(FALHA_PODMAN_BUILD="1")
    assert r.returncode == 1
    assert not amb.chamadas("podman tag")
    assert amb.estado_de("failed-commit") == f"{sha}:build"
    assert amb.estado_de("deployed-commit") is None
    assert len(amb.chamadas("curl")) == 1
    assert "DEPLOY FALHOU" in amb.corpo.read_text()
    r2 = amb.rodar(FALHA_PODMAN_BUILD="1")
    assert r2.returncode == 1
    assert len(amb.chamadas("curl")) == 1


def test_falha_de_inicio(amb):
    sha = amb.commit("nao inicia")
    r = amb.rodar(FALHA_SYSTEMCTL_TRY_RESTART="1")
    assert r.returncode == 1
    assert amb.estado_de("failed-commit") == f"{sha}:inicio"
    assert amb.estado_de("deployed-commit") is None


def test_servico_parado_a_mao_conta_como_sucesso_com_nota(amb):
    sha = amb.commit("com servico parado")
    r = amb.rodar(PARADO="1")
    assert r.returncode == 0, _tudo(r)
    assert amb.estado_de("deployed-commit") == sha
    assert "parado manualmente" in amb.corpo.read_text()


def test_sem_webhook_o_deploy_segue_sem_curl(amb):
    amb.webhook(None)
    r = amb.rodar()
    assert r.returncode == 0
    assert amb.estado_de("deployed-commit")
    assert not amb.chamadas("curl")


def test_falha_do_curl_nao_altera_codigo_de_saida(amb):
    r = amb.rodar(FALHA_CURL="1")
    assert r.returncode == 0
    assert amb.estado_de("deployed-commit")


def test_falha_do_git_vira_etapa_download_dedupada_por_causa(amb):
    (amb.config / "repo.conf").write_text(f"REPO_URL={amb.base}/nao-existe\nBRANCH=main\n")
    r = amb.rodar()
    assert r.returncode == 1
    assert amb.estado_de("failed-commit").startswith("download:")
    assert len(amb.chamadas("curl")) == 1
    assert "download" in amb.corpo.read_text()
    amb.rodar()
    assert len(amb.chamadas("curl")) == 1


def test_nenhuma_saida_expoe_segredos(amb):
    amb.commit("x")
    r = amb.rodar(FALHA_PODMAN_BUILD="1")
    saida = _tudo(r)
    assert WEBHOOK not in saida
    assert "usuario:senha@" not in saida
    assert WEBHOOK not in amb.corpo.read_text()


def test_deploy_concorrente_sai_sem_fazer_nada(amb):
    import fcntl

    with open(amb.base / "deploy.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        r = amb.rodar()
    assert r.returncode == 0
    assert not amb.chamadas()
    assert amb.estado_de("last-check") is None


def test_webhook_nao_aparece_no_argv_do_curl(amb):
    amb.commit("y")
    amb.rodar()
    assert not any(WEBHOOK in l for l in amb.chamadas("curl"))
    assert WEBHOOK in amb.stdin_curl.read_text()
