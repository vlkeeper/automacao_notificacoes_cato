<!--
### Sync Impact Report
- Version change: 1.0.0 → 2.0.0 (MAJOR)
- Ratification Date: 2026-09-21 (mantida)
- Last Amended Date: 2026-10-06
- Modified principles:
  - I. Resiliência de Estado (NON-NEGOTIABLE) → I. Resiliência de Estado (INEGOCIÁVEL)
    (adicionadas regras de releitura na inicialização, "enviado" só após sucesso e nova linha de base)
  - II. Operações de Rede Defensivas → V. Rede Defensiva e Entrega Sem Perda
    (renumerado; adicionados backoff para 429/5xx, fila pendente_envio e piso de intervalo)
  - III. Isolamento Estrito de Segredos + IV. Configuração Fail-Fast
    → VI. Segredos Isolados e Configuração Fail-Fast (fundidos; token Cato somente leitura)
  - V. Carga Cognitiva e Fadiga de Alerta → IV. Anti-Fadiga de Alertas
    (adicionadas supressão por site, reavaliação de links e lembrete diário)
- Added principles:
  - II. Falha de Observação Não É Evento Observado (INEGOCIÁVEL)
  - III. Máquina de Estados Explícita e Tempo Determinístico
  - VII. Observabilidade do Próprio Monitor
- Added sections: subseção "Aplicação" em cada princípio
- Removed sections / scope:
  - Canal Meta Cloud API (WhatsApp) removido das Diretrizes Técnicas; Teams (Workflows/webhook) é o
    único canal de notificação
- Renamed headings: "Core Principles" → "Princípios Fundamentais"; "Governance" → "Governança"
- Follow-up TODOs: nenhum placeholder pendente
- Impacto em artefatos existentes (não alterados por este comando):
  - specs/001-cato-socket-monitoring/* referenciava WhatsApp e os 5 princípios antigos;
    novas specs/planos devem verificar conformidade com os 7 princípios
-->

# Monitoramento Cato Networks Constitution

Daemon em Python, executado em contêiner, que consulta a API GraphQL da Cato Networks, detecta
queda e retorno de links (LAN e WAN) e de sites, e notifica a equipe via Microsoft Teams
(Workflows/webhook).

## Princípios Fundamentais

### I. Resiliência de Estado (INEGOCIÁVEL)

**Regras:**
- O estado DEVE ser persistido em volume, gravado de forma atômica (arquivo `.tmp` seguido de
  substituição, ex.: `os.replace`) e relido na inicialização.
- Um reinício do contêiner NÃO DEVE reenviar notificações já enviadas nem zerar tolerâncias em
  andamento.
- Um evento só DEVE ser marcado como "enviado" após o sucesso do envio.
- Estado ausente ou corrompido DEVE resultar em nova linha de base: registrar a situação atual sem
  disparar alertas em massa.

**Justificativa:** contêineres reiniciam; sem estado confiável, cada restart gera alertas
duplicados ou perde o "desde quando".

**Aplicação:**
- O caminho do arquivo de estado DEVE apontar para um volume montado, nunca para a camada gravável
  da imagem.
- Testes DEVEM cobrir: interrupção durante a escrita (o arquivo anterior permanece íntegro),
  reinício no meio de uma tolerância (o prazo continua a partir do timestamp persistido) e arquivo
  corrompido (linha de base registrada, zero notificações de queda no primeiro ciclo).

### II. Falha de Observação Não É Evento Observado (INEGOCIÁVEL)

**Regras:**
- Erro de API, timeout ou resposta inválida da Cato NÃO DEVE alterar o estado de nenhum site ou
  link.
- O resultado da consulta DEVE ser tratado separadamente do estado do link.
- Após 5 ciclos consecutivos com erro, o sistema DEVE emitir um alerta sobre o próprio monitor, com
  texto distinto dos alertas de link.

**Justificativa:** sem isso, uma instabilidade da API vira "todos os sites offline".

**Aplicação:**
- O cliente da Cato DEVE retornar um resultado tipado (sucesso com dados validados ou falha com
  motivo); a máquina de estados só DEVE ser alimentada com sucessos.
- Uma resposta sem um site ou link esperado DEVE ser tratada como observação inválida daquele item,
  não como "offline".
- O contador de erros consecutivos DEVE ser persistido e zerado no primeiro ciclo bem-sucedido; o
  alerta do monitor DEVE ser enviado no máximo uma vez por sequência de falhas, com aviso de
  recuperação ao normalizar.

### III. Máquina de Estados Explícita e Tempo Determinístico

**Regras:**
- Todo site e link DEVE estar em um estado nomeado: `ONLINE`, `PENDENTE_OFFLINE` ou
  `OFFLINE_NOTIFICADO`.
- Toda notificação DEVE nascer de uma transição documentada; a transição para `ONLINE` só gera
  aviso de retorno se a queda foi notificada.
- A lógica de transição DEVE ser uma função pura:
  `proximo_estado(estado, observacao, agora)` retorna `(novo_estado, acoes)`.
- Timestamps internos DEVEM ser UTC; o fuso `America/Sao_Paulo` DEVE ser usado apenas para o
  lembrete diário e para exibição.
- O relógio DEVE ser injetável e as durações DEVEM ser calculadas por timestamps, nunca por
  contagem de ciclos.

**Justificativa:** tolerância e lembrete diário são regras de tempo e estado, onde estão os bugs
mais caros.

**Aplicação:**
- A tabela de transições (estado × observação → novo estado + ações) DEVE estar documentada na
  spec e coberta por testes unitários, um por transição.
- A função de transição NÃO DEVE fazer I/O, ler o relógio do sistema nem acessar variáveis
  globais; efeitos (enviar, gravar) são executados pelo laço principal a partir das `acoes`.
- Timestamps persistidos DEVEM ser ISO 8601 com offset UTC explícito.

### IV. Anti-Fadiga de Alertas

**Regras:**
- A notificação de queda SÓ DEVE ocorrer após a tolerância configurada (padrão de 3 minutos) no
  estado persistido, no máximo uma vez por episódio.
- A mensagem DEVE distinguir `LINK OFFLINE` (degradação parcial) de `SITE OFFLINE` (degradação
  total).
- Se o site está offline, alertas individuais de link desse site DEVEM ser suprimidos; a avaliação
  segue a ordem site, depois links.
- Ao retorno do site, os links DEVEM ser reavaliados para não perder um que continue inativo.
- O lembrete diário (até as 08:00) SÓ DEVE ser enviado se houver links inativos, informando desde
  quando, no máximo uma vez por dia.

**Justificativa:** alertas em excesso treinam a equipe a ignorar o canal, e uma queda total não
deve virar dezenas de mensagens.

**Aplicação:**
- Oscilações que retornam a `ONLINE` antes do fim da tolerância NÃO DEVEM gerar mensagem alguma.
- A data do último lembrete diário DEVE ser persistida (no fuso `America/Sao_Paulo`) para garantir
  a regra de "uma vez por dia" mesmo após reinícios.
- Testes DEVEM cobrir: flapping abaixo da tolerância, queda de site com vários links (uma única
  mensagem), retorno do site com link ainda inativo e lembrete diário com e sem links inativos.

### V. Rede Defensiva e Entrega Sem Perda

**Regras:**
- Toda chamada externa (Cato e Teams) DEVE ter timeout explícito e tratamento de erro próprio.
- Respostas 429 e 5xx DEVEM acionar backoff exponencial com limite.
- Falha ao enviar ao Teams NÃO DEVE descartar o evento: ele DEVE ficar como `pendente_envio` e ser
  reenviado nos ciclos seguintes.
- O intervalo de consulta DEVE ser configurável, com piso validado na inicialização.

**Justificativa:** dependências externas falham de forma transitória, e um alerta de queda perdido
é o pior defeito de um monitor.

**Aplicação:**
- Nenhuma exceção de rede PODE encerrar o laço principal; erros são capturados no cliente,
  registrados de forma sanitizada e refletidos no resultado da chamada.
- O backoff DEVE respeitar `Retry-After` quando presente e ter teto de espera e de tentativas por
  ciclo.
- A fila `pendente_envio` DEVE ser persistida junto ao estado (Princípio I) e preservar a ordem dos
  eventos.
- Testes com mock HTTP DEVEM cobrir timeout, 429, 5xx e falha de envio seguida de reenvio.

### VI. Segredos Isolados e Configuração Fail-Fast

**Regras:**
- Segredos (token da Cato, URL do webhook do Teams) DEVEM vir exclusivamente de variáveis de
  ambiente, nunca do código, da imagem ou de logs.
- Logs e mensagens de exceção NÃO DEVEM expor tokens nem URLs completas de webhook.
- Toda a configuração DEVE ser validada na inicialização; valor ausente ou inválido DEVE encerrar o
  processo com `exit 1` e mensagem clara.
- O token da Cato DEVE ter permissão somente leitura.

**Justificativa:** a URL do webhook funciona como senha, e um daemon que sobe mal configurado falha
em silêncio.

**Aplicação:**
- Arquivos `.env` DEVEM estar no `.gitignore` e no `.dockerignore`; o `Dockerfile` NÃO DEVE conter
  `ENV` ou `ARG` com segredos.
- Qualquer exibição de configuração DEVE mascarar segredos (ex.: apenas os 4 últimos caracteres do
  token; apenas o host da URL do webhook).
- Testes DEVEM verificar `exit 1` para cada variável obrigatória ausente ou malformada e a ausência
  de segredos na saída de log.

### VII. Observabilidade do Próprio Monitor

**Regras:**
- O monitor DEVE emitir logs estruturados por ciclo (duração, sites consultados, erros).
- O contêiner DEVE ter healthcheck baseado na idade do último ciclo concluído.
- O monitor DEVE enviar um heartbeat periódico a um serviço externo, que alerte caso os sinais
  deixem de chegar.

**Justificativa:** um monitor travado parece "tudo ok"; é preciso que algo externo perceba quando
ele para.

**Aplicação:**
- Ao fim de cada ciclo, o monitor DEVE gravar o timestamp de conclusão em local lido pelo
  healthcheck; o limite de idade DEVE ser derivado do intervalo de consulta configurado.
- O heartbeat DEVE ser enviado somente após ciclo concluído e sua falha NÃO DEVE interromper o
  monitoramento.
- A URL do serviço de heartbeat é tratada como segredo (Princípio VI).

## Diretrizes Técnicas e Operacionais

- **Ambiente de execução**: contêiner Docker executando um processo Python contínuo, sem
  privilégios elevados, com volume persistente para o arquivo de estado.
- **Integrações**:
  - *Cato Networks GraphQL API*: fonte de telemetria de sites e links LAN/WAN, acessada com token
    somente leitura.
  - *Microsoft Teams (Workflows/webhook)*: único canal de notificação da equipe.
  - *Serviço externo de heartbeat*: detecção de parada do próprio monitor.
- **Configuração**: exclusivamente por variáveis de ambiente, validadas na inicialização
  (Princípio VI).
- **Logs**: estruturados, sanitizados, com registro de ciclo, transições de estado e resultado de
  cada envio.

## Fluxo de Desenvolvimento e Garantia de Qualidade

- **Verificação de conformidade**: todo `spec.md`, `plan.md` e `tasks.md` DEVE conter uma
  verificação explícita contra os sete princípios, apontando qualquer exceção.
- **Testes obrigatórios**:
  - Testes unitários da função de transição com relógio injetado (Princípio III).
  - Testes de persistência atômica, reinício e estado corrompido (Princípio I).
  - Testes de falha de observação e alerta do monitor após 5 erros consecutivos (Princípio II).
  - Testes de supressão, tolerância e lembrete diário (Princípio IV).
  - Testes com mock HTTP para timeout, 429, 5xx e reenvio de `pendente_envio` (Princípio V).
  - Testes de fail-fast e de sanitização de logs (Princípio VI).
- **Critérios de aceite**: nenhuma alteração é aceita se remover timeouts, introduzir estado
  apenas em memória, expor segredos em log, ou gerar notificação fora de uma transição documentada.

## Governança

- Estes princípios prevalecem sobre preferências de implementação; qualquer exceção DEVE ser
  registrada e justificada (no `plan.md`, seção de verificação de conformidade).
- Alterações na constituição DEVEM ser versionadas, com data e motivo, registrados no Sync Impact
  Report da emenda e na mensagem de commit.
- Todo plano e toda tarefa gerados DEVEM ser verificados contra estes princípios.
- **Versionamento semântico**:
  - *MAJOR*: remoção ou redefinição incompatível de princípio ou regra de governança.
  - *MINOR*: novo princípio ou seção, ou ampliação material de orientação existente.
  - *PATCH*: ajustes de redação, correções ortográficas e refinamentos não normativos.
- **Revisão de conformidade**: desenvolvedores e agentes de IA DEVEM atestar a conformidade em cada
  etapa do ciclo (especificação, planejamento, implementação e revisão).

**Version**: 2.0.0 | **Ratified**: 2026-09-21 | **Last Amended**: 2026-10-06
