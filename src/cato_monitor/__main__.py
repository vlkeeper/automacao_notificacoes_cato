"""Ponto de entrada: config → logging → lock → estado → daemon."""

from __future__ import annotations

import logging
import signal
import sys

from . import __version__
from . import estado_store as store
from .cato_client import CatoClient
from .config import carregar_config
from .daemon import Daemon
from .logs import configurar_logging, evento
from .relogio import RelogioSistema


def main() -> int:
    cfg = carregar_config()
    log = configurar_logging(cfg.log_level, cfg.segredos())
    evento(log, logging.INFO, "monitor_iniciando", f"cato-monitor {__version__}",
           versao=__version__, config=cfg.exibicao())

    lock = store.LockInstancia(cfg.state_dir)
    lock.adquirir()  # exit 1 se já houver outra instância

    relogio = RelogioSistema()
    estado, motivo = store.carregar(cfg.state_dir, relogio.agora())
    if motivo is None:
        evento(log, logging.INFO, "estado_carregado", sites=len(estado.sites),
               links=sum(len(s.links) for s in estado.sites.values()),
               pendentes=len(estado.pendente_envio))
    else:
        evento(log, logging.WARNING, "linha_base", "estado vazio: nova linha de base", motivo=motivo)

    daemon = Daemon(cfg, estado, CatoClient(cfg), relogio)
    sinal_recebido: list[str] = []

    def encerrar(signum, _frame):
        sinal_recebido.append(signal.Signals(signum).name)
        daemon.parar()

    signal.signal(signal.SIGTERM, encerrar)
    signal.signal(signal.SIGINT, encerrar)

    try:
        daemon.run()
    finally:
        evento(log, logging.INFO, "monitor_encerrando", sinal=(sinal_recebido or [None])[0])
        lock.liberar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
