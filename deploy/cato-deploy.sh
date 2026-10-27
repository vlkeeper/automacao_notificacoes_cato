#!/usr/bin/env bash
# Deploy automático do monitor: compara a branch remota com o commit implantado, reconstrói a imagem
# e reinicia o serviço. Executado pelo cato-deploy.service (timer). Contrato: deploy-automatico.md.
set -u -o pipefail

CONFIG_DIR="${CATO_CONFIG_DIR:-/etc/cato-monitor}"
STATE_DIR="${CATO_STATE_DIR:-/var/lib/cato-monitor}"
REPO_DIR="${CATO_REPO_DIR:-/opt/cato-monitor/repo}"
LOCK_FILE="${CATO_LOCK_FILE:-/run/cato-deploy.lock}"
IMAGEM="localhost/cato-monitor"
SERVICO="cato-monitor.service"

log() { printf '%s\n' "$*"; }

# Remove credenciais embutidas em URLs (://usuario:senha@) de qualquer texto de erro.
sanitizar() { sed -E 's#://[^/@[:space:]]*@#://#g'; }

agora() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Escrita atômica: .tmp + mv.
gravar() {
    printf '%s\n' "$2" > "$STATE_DIR/$1.tmp" && mv -f "$STATE_DIR/$1.tmp" "$STATE_DIR/$1"
}

ler() { [ -s "$STATE_DIR/$1" ] && head -n 1 "$STATE_DIR/$1" || true; }

# Lê só uma chave de um arquivo KEY=VALUE, sem executá-lo.
chave() {
    [ -r "$2" ] || return 0
    grep -m1 "^$1=" "$2" | cut -d= -f2- | sed -E "s/^[\"']//; s/[\"']\$//" || true
}

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR" 2>/dev/null || true

# 1. Instância única do deploy.
exec 9> "$LOCK_FILE" || exit 1
if ! flock -n 9; then
    log "deploy já em execução; nada a fazer"
    exit 0
fi

# 2. Última verificação.
gravar last-check "$(agora)"

REPO_URL="$(chave REPO_URL "$CONFIG_DIR/repo.conf")"
BRANCH="$(chave BRANCH "$CONFIG_DIR/repo.conf")"
BRANCH="${BRANCH:-main}"
CRED="$CONFIG_DIR/gitlab-credentials"
WEBHOOK="$(chave TEAMS_WEBHOOK_OPERACIONAL_URL "$CONFIG_DIR/.env")"

git_seguro() {
    GIT_TERMINAL_PROMPT=0 git -c credential.helper="store --file=$CRED" "$@"
}

# Envia o card ao canal operacional. Falha só vai ao journal. URL entra por stdin (curl --config -),
# nunca como argumento.
avisar() {
    local titulo="$1" cor="$2"; shift 2
    if [ -z "$WEBHOOK" ]; then
        log "webhook operacional ausente no .env; aviso '$titulo' não enviado"
        return 0
    fi
    local fatos="[]" nome valor
    while [ $# -ge 2 ]; do
        nome="$1"; valor="$2"; shift 2
        fatos="$(jq -c --arg n "$nome" --arg v "$valor" '. + [{title: $n, value: $v}]' <<< "$fatos")"
    done
    local corpo
    corpo="$(jq -nc --arg t "$titulo" --arg c "$cor" --argjson f "$fatos" '{
        type: "message",
        attachments: [{contentType: "application/vnd.microsoft.card.adaptive", contentUrl: null,
          content: {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            type: "AdaptiveCard", version: "1.4",
            body: [{type: "TextBlock", text: $t, weight: "Bolder", size: "Medium", color: $c, wrap: true},
                   {type: "FactSet", facts: $f}]}}]}')" || { log "falha ao montar o aviso"; return 0; }
    if ! printf 'url = "%s"\n' "$WEBHOOK" \
        | curl -sS --fail --max-time 10 --config - -X POST -H 'Content-Type: application/json' \
            --data-binary "$corpo" -o /dev/null 2>&1 | sed "s#$WEBHOOK#<webhook>#g" | sanitizar >&2; then
        log "falha ao enviar o aviso '$titulo'"
    fi
    return 0
}

quando() { TZ=America/Sao_Paulo date '+%d/%m/%Y %H:%M'; }

falhar() {  # falhar <etapa> <sha|""> <detalhe>
    local etapa="$1" sha="$2" detalhe="$3" rotulo marca
    detalhe="$(printf '%s' "$detalhe" | sanitizar | tail -n 1 | cut -c1-200)"
    log "deploy falhou na etapa $etapa: $detalhe"
    case "$etapa" in
        download) rotulo="download" ;;
        build) rotulo="build" ;;
        *) rotulo="início do serviço" ;;
    esac
    if [ "$etapa" = download ] && [ -z "$sha" ]; then
        marca="download:$(printf '%s' "$detalhe" | cksum | cut -d' ' -f1)"
    else
        marca="$sha:$etapa"
    fi
    exibe="indisponível"
    [ -z "$sha" ] || exibe="${sha:0:7}"
    if [ "$(ler failed-commit)" != "$marca" ]; then
        avisar "DEPLOY FALHOU" Attention \
            "Commit" "$exibe" \
            "Etapa" "$rotulo" \
            "Detalhe" "$detalhe"
        gravar failed-commit "$marca"
    fi
    exit 1
}

if [ -z "$REPO_URL" ]; then
    falhar download "" "REPO_URL ausente em $CONFIG_DIR/repo.conf"
fi

# 3. Commit remoto.
if ! saida="$(git_seguro ls-remote "$REPO_URL" "refs/heads/$BRANCH" 2>&1)"; then
    falhar download "" "$saida"
fi
novo="$(printf '%s' "$saida" | awk 'NR==1 {print $1}')"
[ -n "$novo" ] || falhar download "" "branch $BRANCH não encontrada"

# 4. Sem novidade.
if [ "$novo" = "$(ler deployed-commit)" ]; then
    exit 0
fi

# 5. Código novo.
if [ -d "$REPO_DIR/.git" ]; then
    saida="$(git_seguro -C "$REPO_DIR" fetch --quiet "$REPO_URL" "$BRANCH" 2>&1 \
        && git -C "$REPO_DIR" reset --hard --quiet FETCH_HEAD 2>&1)" || falhar download "$novo" "$saida"
else
    mkdir -p "$(dirname "$REPO_DIR")"
    saida="$(git_seguro clone --quiet --branch "$BRANCH" "$REPO_URL" "$REPO_DIR" 2>&1)" \
        || falhar download "$novo" "$saida"
    git -C "$REPO_DIR" reset --hard --quiet "$novo" 2>/dev/null || true
fi
titulo="$(git -C "$REPO_DIR" log -1 --format=%s 2>/dev/null || true)"
curto="${novo:0:12}"

# 6. Build; `latest` só se move depois do sucesso.
saida="$(cd "$REPO_DIR" && podman build --format docker \
    --label "org.opencontainers.image.revision=$novo" \
    -t "$IMAGEM:$curto" -f Containerfile . 2>&1)" || falhar build "$novo" "$saida"
podman tag "$IMAGEM:$curto" "$IMAGEM:latest" || falhar build "$novo" "falha ao marcar latest"

# 7. Reinício.
nota=""
if systemctl is-active --quiet "$SERVICO"; then
    estava_ativo=1
else
    estava_ativo=0
    nota="Imagem atualizada; serviço parado manualmente, não foi iniciado."
fi
saida="$(systemctl try-restart "$SERVICO" 2>&1)" || falhar inicio "$novo" "$saida"
if [ "$estava_ativo" = 1 ]; then
    ok=0
    for _ in $(seq 1 60); do
        if systemctl is-active --quiet "$SERVICO"; then ok=1; break; fi
        sleep 1
    done
    [ "$ok" = 1 ] || falhar inicio "$novo" "serviço não ficou ativo em 60 s"
    sleep "${CATO_ESTABILIDADE_S:-10}"
    systemctl is-active --quiet "$SERVICO" || falhar inicio "$novo" "serviço caiu logo após iniciar"
fi

# 8. Sucesso.
gravar deployed-commit "$novo"
gravar last-deploy "$(agora)"
rm -f "$STATE_DIR/failed-commit"
podman image prune -f >/dev/null 2>&1 || true
podman images --format '{{.Tag}}' "$IMAGEM" 2>/dev/null | grep -E '^[0-9a-f]{12}$' | tail -n +3 \
    | while read -r tag; do podman rmi "$IMAGEM:$tag" >/dev/null 2>&1 || true; done
log "deploy concluído: $novo"
if [ -n "$nota" ]; then
    avisar "DEPLOY CONCLUÍDO" Good "Commit" "${novo:0:7} — $titulo" "Quando" "$(quando)" "Observação" "$nota"
else
    avisar "DEPLOY CONCLUÍDO" Good "Commit" "${novo:0:7} — $titulo" "Quando" "$(quando)"
fi
exit 0
