# Data Model: artefatos e estado de implantação

Não há mudança no modelo de dados do monitor (`state.json`, fila, `last_cycle` seguem como estão em
`/data`). Esta feature adiciona apenas o estado do deploy e a definição do serviço.

## Estado do deploy (host, `/var/lib/cato-monitor/`, root, 0700)

| Arquivo | Conteúdo | Escrito quando | Uso |
|---|---|---|---|
| `deployed-commit` | SHA completo do último commit implantado com sucesso | fim de deploy bem-sucedido | decide se há commit novo (FR-026); mostra o commit em execução (FR-031) |
| `failed-commit` | `<sha>:<etapa>` do último deploy que falhou e já foi avisado (`etapa` ∈ `download`, `build`, `inicio`) | após avisar uma falha | dedup do aviso (FR-029) |
| `last-check` | timestamp UTC ISO 8601 da última verificação | toda execução | FR-031 |
| `last-deploy` | timestamp UTC ISO 8601 do último deploy bem-sucedido | sucesso | FR-031 |

Escrita atômica (`.tmp` + `mv`), mesmo critério do princípio I. Se um arquivo faltar ou estiver vazio,
vale "nunca implantado/nunca falhou" (primeira execução implanta o HEAD e avisa sucesso).

### Transições

```text
(sem commit novo)            → atualiza last-check; fim
commit novo → download falha → failed-commit=<sha ou causa>:download (avisa se mudou); exit 1
            → build falha    → failed-commit=<sha>:build   (avisa se mudou); exit 1
            → restart falha  → failed-commit=<sha>:inicio  (avisa se mudou); exit 1
            → ok             → deployed-commit=<sha>; last-deploy; remove failed-commit; avisa sucesso
```

Um novo `<sha>` ou nova etapa gera novo aviso. Repetir o mesmo valor não gera.

## Entidades de execução

- **Imagem**: `localhost/cato-monitor:<sha12>` e `:latest`; label `org.opencontainers.image.revision`.
- **Container**: `cato-monitor` (nome fixo, `--rm`), recriado a cada start do serviço.
- **Volume**: `cato-monitor-data` (UID/GID 10001), montado em `/data`; sobrevive a tudo, exceto à
  desinstalação explícita (`podman volume rm`).
- **Arquivos de host** (`/etc/cato-monitor/`, root): `.env` (0600, segredos do monitor),
  `gitlab-credentials` (0600), `repo.conf` (0644: `REPO_URL`, `BRANCH`; sem segredos).
- **Clone**: `/opt/cato-monitor/repo` (inclui `certs/` no host, não versionado além do README).
