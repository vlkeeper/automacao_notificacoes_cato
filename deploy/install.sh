#!/usr/bin/env bash
# Instala as unidades do monitor e do deploy automático no host. Idempotente; não sobrescreve
# .env, repo.conf nem gitlab-credentials existentes e não habilita nem inicia nada.
set -eu -o pipefail

[ "$(id -u)" -eq 0 ] || { echo "execute como root (sudo)" >&2; exit 1; }

ORIGEM="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install -d -m 0755 /etc/containers/systemd /etc/cato-monitor /usr/local/lib/cato-monitor
install -d -m 0700 /var/lib/cato-monitor

install -m 0644 "$ORIGEM/cato-monitor.container" "$ORIGEM/cato-monitor.volume" /etc/containers/systemd/
install -m 0644 "$ORIGEM/journald@cato-monitor.conf" /etc/systemd/
install -m 0644 "$ORIGEM/cato-deploy.service" "$ORIGEM/cato-deploy.timer" /etc/systemd/system/
install -m 0755 "$ORIGEM/cato-deploy.sh" /usr/local/lib/cato-monitor/cato-deploy.sh

if [ ! -e /etc/cato-monitor/repo.conf ]; then
    printf 'REPO_URL=\nBRANCH=main\n' > /etc/cato-monitor/repo.conf
    chmod 0644 /etc/cato-monitor/repo.conf
fi
if [ ! -e /etc/cato-monitor/gitlab-credentials ]; then
    install -m 0600 /dev/null /etc/cato-monitor/gitlab-credentials
fi

systemctl daemon-reload
echo "Unidades instaladas. Próximos passos: /etc/cato-monitor/.env, build da imagem e 'systemctl start cato-monitor' (o boot é automático; não use enable) (veja o README)."
