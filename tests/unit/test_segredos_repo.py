"""Princípio VI: nenhum segredo no repositório nem na imagem."""

import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).parents[2]
PALAVRAS_SECRETAS = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|WEBHOOK|HEARTBEAT)", re.IGNORECASE)


def linhas(arquivo: str) -> list[str]:
    return (RAIZ / arquivo).read_text(encoding="utf-8").splitlines()


def test_dockerfile_sem_env_ou_arg_de_segredo():
    for linha in linhas("Dockerfile"):
        if re.match(r"\s*(ENV|ARG)\b", linha, re.IGNORECASE):
            assert not PALAVRAS_SECRETAS.search(linha), f"segredo no Dockerfile: {linha}"


@pytest.mark.parametrize("arquivo", [".gitignore", ".dockerignore"])
def test_ignore_files_excluem_env(arquivo):
    conteudo = linhas(arquivo)
    assert ".env" in conteudo
    assert any(l.strip() == ".env.*" for l in conteudo)


def test_dockerignore_exclui_artefatos_sensiveis_e_de_desenvolvimento():
    conteudo = "\n".join(linhas(".dockerignore"))
    for padrao in (".git", "tests/", "specs/", ".specify/", ".claude/", ".venv/"):
        assert padrao in conteudo, f"{padrao} ausente do .dockerignore"


def test_compose_nao_traz_segredos_e_usa_env_file():
    texto = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert "env_file: .env" in texto
    assert "replicas" not in texto.replace("não use deploy.replicas", "")


def _valores_do_env() -> list[str]:
    env = RAIZ / ".env"
    if not env.exists():
        pytest.skip(".env ausente (como no CI)")
    valores = []
    for linha in env.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            valor = linha.split("=", 1)[1].strip().strip("\"'")
            if len(valor) >= 8:  # ignora valores triviais (ex.: 60, INFO)
                valores.append(valor)
    return valores


def test_nenhum_valor_do_env_em_arquivos_versionados():
    valores = _valores_do_env()
    try:
        saida = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard"], cwd=RAIZ, capture_output=True, text=True, check=True
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git indisponível")
    for nome in saida:
        caminho = RAIZ / nome
        if not caminho.is_file() or caminho.name == ".env":
            continue
        try:
            texto = caminho.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for valor in valores:
            assert valor not in texto, f"valor do .env encontrado em {nome}"
