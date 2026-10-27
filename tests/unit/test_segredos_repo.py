"""Princípio VI: nenhum segredo no repositório nem na imagem."""

import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).parents[2]
PALAVRAS_SECRETAS = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|WEBHOOK|HEARTBEAT)", re.IGNORECASE)


def linhas(arquivo: str) -> list[str]:
    return (RAIZ / arquivo).read_text(encoding="utf-8").splitlines()


def test_containerfile_sem_env_ou_arg_de_segredo():
    for linha in linhas("Containerfile"):
        if re.match(r"\s*(ENV|ARG)\b", linha, re.IGNORECASE):
            assert not PALAVRAS_SECRETAS.search(linha), f"segredo no Containerfile: {linha}"


@pytest.mark.parametrize("arquivo", [".gitignore", ".containerignore"])
def test_ignore_files_excluem_env(arquivo):
    conteudo = linhas(arquivo)
    assert ".env" in conteudo
    assert any(l.strip() == ".env.*" for l in conteudo)


def test_containerignore_exclui_artefatos_sensiveis_e_de_desenvolvimento():
    conteudo = "\n".join(linhas(".containerignore"))
    for padrao in (".git", "tests/", "specs/", ".specify/", ".claude/", ".venv/"):
        assert padrao in conteudo, f"{padrao} ausente do .containerignore"


def _valores_do_env() -> list[str]:
    env = RAIZ / ".env"
    if not env.exists():
        pytest.skip(".env ausente (como no CI)")
    valores = []
    for linha in env.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            chave, valor = (parte.strip() for parte in linha.split("=", 1))
            valor = valor.strip("\"'")
            # só chaves sensíveis: TZ, STATE_DIR etc. aparecem legitimamente no .env.example
            sensivel = any(marca in chave.upper() for marca in ("KEY", "TOKEN", "SECRET", "URL"))
            if sensivel and len(valor) >= 8:
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


def test_deploy_nao_contem_valores_do_env():
    valores = _valores_do_env()
    for arquivo in (RAIZ / "deploy").iterdir():
        texto = arquivo.read_text(encoding="utf-8")
        for valor in valores:
            assert valor not in texto, f"valor do .env em deploy/{arquivo.name}"


def test_deploy_sem_url_literal_de_webhook_ou_credencial():
    for arquivo in (RAIZ / "deploy").iterdir():
        texto = arquivo.read_text(encoding="utf-8")
        assert not re.search(r"https://[^\s/@:]+:[^\s/@]+@", texto), f"credencial em {arquivo.name}"
        assert not re.search(r"https?://\S*(webhook|logic\.azure|office\.com)\S*", texto, re.I)


def test_script_de_deploy_nao_carrega_env_nem_expoe_webhook():
    texto = (RAIZ / "deploy" / "cato-deploy.sh").read_text(encoding="utf-8")
    codigo = [l for l in texto.splitlines() if not l.lstrip().startswith("#")]
    for linha in codigo:
        assert not re.match(r"\s*(source|\.)\s+\S*\.env", linha), f"source do .env: {linha}"
        if re.match(r"\s*(echo|printf)", linha):
            assert "$WEBHOOK" not in linha or "curl" in linha, f"webhook impresso: {linha}"
        if re.search(r"curl", linha):
            assert "$WEBHOOK" not in linha.split("curl", 1)[1], f"webhook no argv do curl: {linha}"
