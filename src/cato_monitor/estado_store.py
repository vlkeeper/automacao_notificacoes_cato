"""Persistência do estado: JSON atômico, last_cycle e lock de instância única."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from .logs import evento
from .modelos import (
    SCHEMA_VERSION,
    EstadoMonitor,
    ts_para_str,
    verificar_invariantes,
)

NOME_ESTADO = "state.json"
NOME_LAST_CYCLE = "last_cycle"
NOME_LOCK = "monitor.lock"

log = logging.getLogger("cato_monitor.estado")


def _fsync_diretorio(pasta: Path) -> None:
    try:  # em Windows não é possível abrir diretório; ignora
        fd = os.open(pasta, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _gravar_atomico(destino: Path, conteudo: str) -> None:
    tmp = destino.with_name(destino.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(conteudo)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, destino)
    _fsync_diretorio(destino.parent)


def salvar(estado: EstadoMonitor, state_dir: Path, agora: datetime) -> None:
    estado.atualizado_em = agora
    conteudo = json.dumps(estado.para_dict(), ensure_ascii=False, indent=2)
    _gravar_atomico(Path(state_dir) / NOME_ESTADO, conteudo)


def gravar_last_cycle(state_dir: Path, agora: datetime) -> None:
    _gravar_atomico(Path(state_dir) / NOME_LAST_CYCLE, ts_para_str(agora) + "\n")


def _preservar_corrompido(arquivo: Path, agora: datetime) -> Path:
    marca = agora.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = arquivo.with_name(f"{arquivo.name}.corrompido-{marca}")
    os.replace(arquivo, destino)
    return destino


def carregar(state_dir: Path, agora: datetime) -> tuple[EstadoMonitor, str | None]:
    """Lê o estado. Devolve (estado, motivo_linha_base).

    `motivo_linha_base` é None quando o estado foi carregado; senão, o estado devolvido é vazio
    (nova linha de base, R-004) e o arquivo ruim, se existia, foi preservado como
    `state.json.corrompido-<UTC>`. `schema_version` maior que o suportado encerra com exit 1.
    """
    arquivo = Path(state_dir) / NOME_ESTADO
    if not arquivo.exists():
        return EstadoMonitor(), "arquivo_ausente"

    motivo = None
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        if not isinstance(dados, dict):
            raise ValueError("raiz não é objeto")
        versao = dados.get("schema_version")
        if isinstance(versao, int) and not isinstance(versao, bool) and versao > SCHEMA_VERSION:
            evento(
                log, logging.ERROR, "schema_estado_futuro",
                f"state.json tem schema_version={versao}, suportado até {SCHEMA_VERSION}",
            )
            raise SystemExit(1)
        if versao != SCHEMA_VERSION:
            raise ValueError("schema_version ausente ou inválido")
        estado = EstadoMonitor.de_dict(dados)
        violacoes = verificar_invariantes(estado)
        if violacoes:
            raise ValueError("invariantes violadas: " + "; ".join(violacoes[:3]))
        return estado, None
    except SystemExit:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        motivo = f"estado_invalido: {type(exc).__name__}"

    try:
        preservado = _preservar_corrompido(arquivo, agora)
        evento(log, logging.WARNING, "estado_corrompido", f"arquivo preservado em {preservado.name}")
    except OSError:
        evento(log, logging.WARNING, "estado_corrompido", "não foi possível preservar o arquivo ruim")
    return EstadoMonitor(), motivo


class LockInstancia:
    """Lock exclusivo de `monitor.lock`, mantido aberto durante a vida do processo."""

    def __init__(self, state_dir: Path):
        self.caminho = Path(state_dir) / NOME_LOCK
        self._arquivo: IO[bytes] | None = None

    def adquirir(self) -> None:
        arquivo = open(self.caminho, "a+b")
        try:
            if os.name == "nt":
                import msvcrt

                arquivo.seek(0)
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            arquivo.close()
            evento(log, logging.ERROR, "instancia_duplicada", "outra instância está em execução",
                   lock=str(self.caminho))
            raise SystemExit(1)
        self._arquivo = arquivo

    def liberar(self) -> None:
        if self._arquivo is not None:
            self._arquivo.close()
            self._arquivo = None
