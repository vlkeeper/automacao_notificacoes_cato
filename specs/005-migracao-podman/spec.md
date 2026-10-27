# Feature Specification: Migração da execução de Docker para Podman

**Feature Branch**: `005-migracao-podman`

**Created**: 2026-10-27

**Status**: Draft

**Input**: User description: "Migrar a execução da automação de Docker/docker-compose para Podman (versão 5.7.0), mantendo 100% das funcionalidades operacionais atuais: reinício automático e retorno após reboot; mesmo healthcheck (`cato_monitor.healthcheck`, mesmos intervalo/timeout/início/tentativas, sem reinício quando unhealthy); instância única via `/data/monitor.lock`; SIGTERM ao processo com 30 s de tolerância; hardening (raiz somente leitura, `/tmp` em tmpfs, sem capabilities, no-new-privileges, UID 10001); segredos só via `.env`; persistência de `/data` com migração do volume `monitor-data`; logs com rotação 10 MB x 5; build com base por digest, dependências com hash e CAs de `certs/`. Ambiente: VM Ubuntu Server 26 (systemd 259), sem interface gráfica, via SSH; Podman é o único runtime; serviço gerenciado pelo systemd, sobe no boot sem login, reinicia em falha, controlado por systemctl/journalctl. `systemctl stop` mantém parado até novo start; após reboot o serviço habilitado sobe (diferença aceita em relação ao unless-stopped). Fora do escopo: mudar o comportamento do código Python."

## Clarifications

### Session 2026-10-27

- Q: O Podman deve rodar como root no host (rootful) ou sem root sob usuário dedicado (rootless)? → A: Rootful: o Podman roda como root no host; o container mantém UID 10001 e todo o hardening atual.
- Q: Os logs vão para o journal do systemd ou para arquivos do Podman com rotação 10 MB x 5? → A: Journal (driver journald), consultável por `journalctl -u` e `podman logs`, com retenção limitada a ~50 MB para os logs do serviço (substitui a rotação 10 MB x 5 em arquivo).
- Q: Existe instalação Docker na VM cujo estado precise ser migrado? → A: Não. A versão com Docker roda só na máquina do desenvolvedor; a VM recebe uma instalação nova, com `/data` vazio. Não há migração de volume nem remoção de Docker na VM (substitui a resposta anterior sobre remover o Docker e o volume antigo após a validação).
- Q: Onde a imagem é construída? → A: Na própria VM, a partir do código clonado no host (como o código chega e é atualizado ficou definido na pergunta sobre deploy automático, abaixo).
- Q: Em falhas seguidas ao iniciar, o systemd tenta para sempre ou desiste? → A: Tenta para sempre, com 30 s entre as tentativas, sem limite de tentativas.
- Q: Rodar a automação em container na máquina Windows do desenvolvedor faz parte desta feature? → A: Não. O único caminho de execução documentado é a VM Ubuntu com systemd; localmente o desenvolvimento usa só Python/pytest, sem container.
- Q: Como uma mudança na branch principal chega à automação na VM? → A: Deploy automático por verificação periódica: a VM consulta a branch principal do repositório no GitLab da empresa a cada 5 min, com token somente leitura; havendo commit novo, baixa, reconstrói a imagem e reinicia o serviço. Se falhar, mantém a versão atual, registra no journal/status do systemd e avisa no canal operacional do Teams (`TEAMS_WEBHOOK_OPERACIONAL_URL`) uma vez por commit; o deploy bem-sucedido também é avisado ali.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operar a automação só com Podman e systemd (Priority: P1)

Como operador da VM (acesso por SSH), quero instalar, subir, parar, ver logs e ver o status de saúde da automação usando apenas Podman e os comandos do systemd (`systemctl`, `journalctl`), sem Docker instalado no host, para que o monitor siga funcionando exatamente como hoje.

**Why this priority**: É o objetivo central da feature. Sem isso, a automação não roda na VM, que não tem Docker.

**Independent Test**: Em uma VM limpa com Ubuntu Server 26 e Podman 5.7.0 (sem Docker), seguir o README para construir a imagem e instalar o serviço; verificar que o monitor executa ciclos normalmente, que `systemctl status` mostra o serviço ativo, que `journalctl` mostra os logs JSON do monitor e que o status de saúde fica "healthy" após o período de início.

**Acceptance Scenarios**:

1. **Given** uma VM com Podman 5.7.0, sem Docker, com o código e o `.env` preenchido, **When** o operador executa o procedimento de instalação do README, **Then** a imagem é construída e o serviço fica ativo e habilitado para iniciar no boot.
2. **Given** o serviço ativo, **When** o operador consulta os logs pelo `journalctl` (e pelo Podman), **Then** vê as linhas de log do monitor em tempo real.
3. **Given** o serviço ativo há mais que o período de início, **When** o operador consulta o status de saúde, **Then** o container aparece como "healthy" enquanto os ciclos estiverem em dia, e "unhealthy" após 3 falhas consecutivas do comando de saúde.
4. **Given** o container marcado como "unhealthy", **When** nenhuma ação é tomada, **Then** o container NÃO é reiniciado automaticamente; o estado apenas fica registrado e visível.
5. **Given** o serviço ativo, **When** o operador executa `systemctl stop`, **Then** o processo recebe SIGTERM, encerra de forma limpa em até 30 s (ou é forçado ao fim desse prazo) e o serviço permanece parado até um novo `systemctl start`.

---

### User Story 2 - Recuperação automática após falha e reboot (Priority: P1)

Como operador, quero que a automação volte sozinha quando o processo cair e quando a VM reiniciar, sem precisar de login de ninguém, para não perder monitoramento em janelas de manutenção ou falhas.

**Why this priority**: O monitor existe para avisar quedas; ficar parado sem ninguém perceber é a pior falha operacional.

**Independent Test**: Matar o processo principal do container e verificar que o serviço é reiniciado; reiniciar a VM sem fazer login e verificar que o monitor volta a executar ciclos.

**Acceptance Scenarios**:

1. **Given** o serviço habilitado e ativo, **When** o processo do monitor termina com erro (ou é morto), **Then** o systemd reinicia o serviço automaticamente.
2. **Given** o serviço habilitado, **When** a VM é reiniciada e ninguém faz login, **Then** o monitor volta a executar ciclos após o boot.
3. **Given** o serviço parado manualmente com `systemctl stop`, mas ainda habilitado, **When** a VM é reiniciada, **Then** o serviço sobe normalmente após o boot (diferença aceita em relação ao `unless-stopped` do Docker).
4. **Given** o serviço parado manualmente e a VM sem reboot, **When** o tempo passa, **Then** o serviço não é reiniciado sozinho.

---

### User Story 3 - Primeira instalação na VM com estado vazio e persistente (Priority: P1)

Como operador, quero instalar a automação pela primeira vez na VM, com o volume de estado vazio, e que esse estado passe a sobreviver a reinícios, reboots e recriações do container, para que o monitor comece do zero uma única vez e nunca mais perca fila ou episódios abertos.

**Why this priority**: A VM não tem instalação anterior (a versão Docker roda só na máquina do desenvolvedor). A constituição exige resiliência de estado e "sem perda" (princípios I e V) a partir da primeira execução.

**Independent Test**: Em uma VM nova, subir o serviço com o volume vazio; verificar que o monitor cria seu estado em `/data` com dono UID 10001 e estabelece a linha de base sem alertas em massa; recriar o container e reiniciar a VM, e verificar que o estado (inclusive a fila) é o mesmo e que nenhuma nova linha de base é criada.

**Acceptance Scenarios**:

1. **Given** uma VM sem nenhuma instalação anterior, **When** o serviço sobe pela primeira vez, **Then** o volume de estado é criado vazio, gravável pelo UID 10001, e o monitor estabelece a linha de base inicial sem enviar alertas de queda em massa (comportamento atual do código).
2. **Given** o monitor já rodando com estado e eventos na fila, **When** o container é removido e recriado (ex.: atualização), **Then** o estado e a fila são lidos de novo e os eventos pendentes são enviados na ordem original.
3. **Given** um arquivo de lock que sobrou de uma execução anterior interrompida, **When** o monitor sobe, **Then** ele adquire o lock normalmente (o lock pertence ao processo, não ao arquivo), sem recusar a inicialização.

---

### User Story 4 - Deploy automático a partir da branch principal (Priority: P2)

Como desenvolvedor, quero que um commit na branch principal do repositório no GitLab da empresa entre em execução na VM sozinho, e que o canal operacional do Teams me avise se o deploy deu certo ou falhou, para não precisar acessar a VM a cada mudança. Como operador, quero também atualizar `.env` e `certs/`, que ficam só no host, com um procedimento documentado, mantendo o estado em `/data`.

**Why this priority**: Atualizações são frequentes, mas menos críticas que subir e recuperar o serviço; o monitor já roda sem o deploy automático.

**Independent Test**: Com o serviço rodando, fazer um commit na branch principal e verificar que, em até 15 min, a VM executa o novo commit, o estado foi preservado e chegou um aviso de sucesso no canal operacional. Depois, fazer um commit que quebra o build e verificar que a versão anterior continua rodando e que chega um único aviso de falha.

**Acceptance Scenarios**:

1. **Given** o monitor rodando o commit X, **When** o commit Y entra na branch principal, **Then** em até 15 min a imagem é reconstruída a partir de Y, o container é recriado, o estado em `/data` é preservado e o canal operacional recebe um aviso de deploy bem-sucedido citando Y.
2. **Given** o commit Z que quebra o build, **When** a verificação tenta implantá-lo, **Then** o monitor continua rodando a versão anterior, a falha aparece no journal e no status do serviço de verificação, e o canal operacional recebe um único aviso de falha citando Z e a etapa.
3. **Given** a falha do commit Z já avisada, **When** as verificações seguintes tentam Z de novo e falham, **Then** nenhum aviso adicional é enviado; **When** um commit de correção entra e é implantado, **Then** chega o aviso de sucesso.
4. **Given** uma alteração no `.env`, **When** o operador reinicia o serviço, **Then** o novo valor passa a valer sem reconstruir a imagem.
5. **Given** uma nova CA em `certs/` no host, **When** a imagem é reconstruída (no próximo deploy ou manualmente), **Then** as chamadas HTTPS que dependem dessa CA passam a funcionar.

---

### User Story 5 - Garantias de segurança e instância única preservadas (Priority: P2)

Como responsável pela segurança do host, quero que o container no Podman tenha o mesmo hardening de hoje e que seja impossível rodar duas instâncias sobre o mesmo estado.

**Why this priority**: São garantias já existentes que não podem regredir, mas não mudam o fluxo diário do operador.

**Independent Test**: Inspecionar o container em execução e conferir raiz somente leitura, `/tmp` em memória, nenhuma capability, no-new-privileges e UID 10001; tentar subir uma segunda instância sobre o mesmo volume e verificar que ela é recusada.

**Acceptance Scenarios**:

1. **Given** o container em execução, **When** o processo tenta gravar fora de `/data` e `/tmp`, **Then** a gravação falha por filesystem somente leitura.
2. **Given** o container em execução, **When** suas configurações de segurança são inspecionadas, **Then** não há capabilities, no-new-privileges está ativo e o processo roda como UID 10001.
3. **Given** uma instância ativa, **When** uma segunda instância é iniciada sobre o mesmo volume `/data`, **Then** a segunda é recusada pelo lock e encerra sem alterar o estado.
4. **Given** a imagem construída, **When** suas camadas e metadados são inspecionados, **Then** não há nenhum segredo do `.env` dentro dela.

---

### Edge Cases

- O Podman na VM está em versão diferente de 5.7.0: o README indica a versão exigida e como conferi-la; o comportamento só é garantido na versão suportada.
- O `.env` está ausente ou ilegível: o serviço falha ao iniciar com mensagem clara no `journalctl` e tenta de novo a cada 30 s, indefinidamente, até o arquivo ser corrigido.
- Configuração inválida no `.env` (processo encerra com `exit 1`): o serviço é reiniciado a cada 30 s, sem limite, e cada erro aparece no `journalctl`; ao corrigir o `.env`, a próxima tentativa sobe sem ação manual.
- Volume de estado sem permissão de escrita para o UID 10001 (ex.: criado manualmente com outro dono): o monitor falha com o erro de `STATE_DIR` não gravável, que já existe; o README indica como corrigir.
- Reboot durante a execução de um ciclo: o estado continua íntegro graças à gravação atômica já existente; o serviço sobe no boot.
- Disco de logs: a retenção no journal limita os logs do serviço a cerca de 50 MB; ao atingir o limite, as entradas mais antigas são descartadas.
- Pasta `certs/` vazia: o build funciona normalmente sem CAs adicionais (comportamento atual).
- GitLab indisponível ou token expirado/revogado: a verificação falha, o monitor segue na versão atual, e a falha é registrada e avisada no Teams uma vez (por causa, não a cada 5 min).
- Commit novo que constrói, mas faz o monitor falhar ao iniciar (ex.: erro de configuração): o deploy é avisado como falha na etapa "início do serviço"; o monitor fica na política de reinício até um commit de correção.
- Vários commits na branch principal entre duas verificações: só o mais recente é implantado.
- Serviço do monitor parado manualmente (`systemctl stop`): o deploy automático reconstrói a imagem, mas não inicia o monitor, respeitando a parada manual (FR-005).
- Commit que altera só arquivos fora da imagem (ex.: `specs/`, README): ainda é tratado como commit novo; a reconstrução aproveita o cache e o reinício é rápido.
- `systemctl stop` durante o envio de um evento: o processo recebe SIGTERM e tem 30 s para encerrar; o que não foi enviado permanece na fila persistida.

## Requirements *(mandatory)*

### Functional Requirements

**Runtime e ciclo de vida**

- **FR-001**: A automação MUST executar com Podman 5.7.0 como único runtime de containers no host; o Docker MUST NOT ser necessário para construir, executar, operar ou atualizar.
- **FR-002**: O serviço MUST ser gerenciado pelo systemd em nível de sistema, controlável com `systemctl` (start, stop, restart, status, enable) e com logs consultáveis pelo `journalctl`.
- **FR-002a**: O Podman MUST executar em modo rootful (como root no host, sem mapeamento de usuários rootless); a imagem, o volume e o container ficam no armazenamento de sistema do Podman. Dentro do container, o processo continua como UID 10001 com todo o hardening de FR-014, e o UID 10001 no volume corresponde ao UID 10001 no host, como no Docker.
- **FR-003**: O serviço habilitado MUST iniciar automaticamente no boot da VM, sem depender de login de nenhum usuário.
- **FR-004**: O serviço MUST ser reiniciado automaticamente pelo systemd quando o processo do monitor terminar com falha, aguardando 30 s entre as tentativas e sem limite de tentativas (o serviço nunca desiste nem fica em estado `failed` por excesso de reinícios).
- **FR-005**: Após `systemctl stop`, o serviço MUST permanecer parado até um novo `systemctl start` ou até o próximo boot (se habilitado).
- **FR-006**: Ao parar o serviço, o SIGTERM MUST chegar ao processo do monitor, que o trata como PID 1 (um processo init foi descartado: com `no-new-privileges` ele não repassa o sinal no Podman 5.7.0, validado na VM em 2026-10-27), e o runtime MUST aguardar 30 s antes de forçar o encerramento.

**Saúde**

- **FR-007**: O container MUST ter healthcheck com o mesmo comando atual (`python -m cato_monitor.healthcheck`) e os mesmos parâmetros: intervalo 60 s, timeout 5 s, período de início 120 s e 3 tentativas.
- **FR-008**: O estado de saúde (healthy/unhealthy/starting) MUST ser consultável pelo operador com Podman.
- **FR-009**: Quando o container ficar unhealthy, o sistema MUST apenas registrar o estado, sem reiniciar, parar ou recriar o container.

**Instância única e estado**

- **FR-010**: Deve existir no máximo uma instância do monitor sobre o volume de estado; o lock existente em `/data/monitor.lock` MUST continuar recusando uma segunda instância.
- **FR-011**: O estado em `/data` MUST ficar em um volume nomeado persistente, que sobrevive à remoção e recriação do container e à atualização da imagem.
- **FR-012**: Na primeira instalação, o volume de estado MUST ser criado vazio e gravável pelo UID 10001, sem nenhum passo manual de ajuste de dono. Não há migração de estado de outra instalação: a VM começa do zero.
- **FR-013**: Remover o container, reconstruir a imagem, reiniciar o serviço ou reiniciar a VM MUST NOT apagar o volume de estado; apagá-lo só pode acontecer por um passo explícito de desinstalação descrito no README.

**Hardening e segredos**

- **FR-014**: O container MUST executar com filesystem raiz somente leitura, `/tmp` em tmpfs, todas as capabilities removidas, no-new-privileges ativo e usuário não-root UID 10001.
- **FR-015**: Segredos MUST ser fornecidos apenas pelo arquivo `.env` no host, carregado como variáveis de ambiente do container; nenhum segredo MUST ser gravado na imagem, no arquivo de definição do serviço ou no repositório.
- **FR-016**: O arquivo `.env` no host MUST ter permissões restritas, e o README MUST indicar quais.
- **FR-017**: A variável `STATE_DIR=/data` MUST continuar definida para o container, como hoje.

**Logs**

- **FR-018**: Os logs do container MUST ir para o journal do systemd e estar acessíveis por `journalctl -u <serviço>` e por `podman logs`. O espaço ocupado pelo journal MUST ficar limitado a ~50 MB (equivalente aos 10 MB x 5 atuais), descartando os mais antigos. *Emenda 2026-10-27:* o limite é o global do journal do host (`SystemMaxUse=50M`), porque o namespace de journal por serviço (`LogNamespace=`) faz o `podman stop` falhar com Podman 5.7.0 rootful.

**Build**

- **FR-019**: A imagem MUST ser construída com Podman a partir do mesmo arquivo de build atual (ou equivalente), mantendo a imagem base fixada por digest, a instalação de dependências com verificação de hash e a inclusão opcional de CAs corporativas da pasta `certs/`.
- **FR-019a**: A imagem MUST ser construída na própria VM, a partir de um clone do repositório no GitLab da empresa e da pasta `certs/` presente no host; não há registro de imagens nem transferência de imagem pronta.

**Deploy automático**

- **FR-025**: A VM MUST verificar a branch principal do repositório no GitLab a cada 5 minutos. A verificação MUST rodar como um serviço do systemd separado do monitor, disparado por timer, sem depender de login e ativo após o boot.
- **FR-026**: Quando houver commit novo na branch principal, a verificação MUST baixar o código, reconstruir a imagem e reiniciar o serviço do monitor para recriar o container com a nova imagem, preservando o volume de estado. Sem commit novo, nada é feito.
- **FR-027**: O acesso ao GitLab MUST usar uma credencial somente leitura (token de deploy ou chave de deploy) guardada na VM, fora do repositório e da imagem, com permissões restritas. Nenhuma conexão de entrada na VM MUST ser exigida.
- **FR-028**: Se o download ou o build falhar, a versão em execução MUST continuar rodando sem interrupção. A falha MUST ser registrada no journal do serviço de verificação, que fica em estado de falha visível em `systemctl`, e a próxima verificação MUST tentar de novo.
- **FR-029**: O resultado de cada deploy MUST ser avisado no canal operacional do Teams (o webhook `TEAMS_WEBHOOK_OPERACIONAL_URL` já presente no `.env`): falha uma única vez por commit (novas tentativas do mesmo commit que falharem de novo não repetem o aviso) e sucesso uma vez por commit implantado. O aviso MUST identificar o commit (hash curto e título) e, na falha, a etapa que falhou (download, build ou início do serviço). Falha ao enviar o aviso MUST NOT impedir nem desfazer o deploy, e o aviso MUST NOT expor segredos.
- **FR-030**: O deploy só é considerado bem-sucedido se o serviço do monitor estiver ativo após o reinício. Não há rollback automático: se a nova versão falhar ao rodar, o monitor segue a política de reinício (FR-004), e a correção é feita com um novo commit (ex.: revert) na branch principal, que a próxima verificação implanta.
- **FR-031**: O operador MUST conseguir ver qual commit está em execução e quando ocorreram a última verificação e o último deploy, e MUST conseguir disparar uma verificação imediata e pausar o deploy automático com comandos do systemd.
- **FR-020**: A imagem MUST manter os mesmos metadados de execução atuais: usuário, healthcheck, ponto de entrada, diretório de trabalho e volume `/data`.

**Documentação e escopo**

- **FR-021**: O README MUST descrever, só com Podman e systemd: pré-requisitos (versão do Podman), build, instalação e habilitação do serviço, start/stop/restart, logs, status de saúde, deploy automático (configurar a credencial do GitLab, acompanhar, forçar e pausar), atualização de `.env` e `certs/` e desinstalação.
- **FR-022**: O README MUST descrever a primeira instalação numa VM nova (instalar o Podman, trazer o código, criar o `.env`, construir, habilitar e validar), incluindo o que esperar na primeira execução (linha de base inicial) e como conferir que o serviço está saudável.
- **FR-023**: Os artefatos exclusivos do Docker MUST ser removidos ou substituídos, para que o repositório tenha um único caminho de execução suportado: o `docker-compose.yml` é removido, o `Dockerfile` passa a se chamar `Containerfile` e o `.dockerignore` passa a se chamar `.containerignore`. Os testes de repositório que verificavam o compose MUST ser substituídos por verificações equivalentes sobre a definição do serviço (segredos só via `.env`, instância única).
- **FR-024**: Nenhum comportamento do código Python da automação MUST mudar; os testes automatizados de comportamento MUST continuar passando sem alteração. Só os testes de repositório que leem arquivos de execução podem ser ajustados aos novos nomes (FR-023).

### Key Entities

- **Imagem da automação**: artefato de execução construído a partir do código, com base fixada por digest, dependências verificadas por hash e CAs opcionais; não contém segredos.
- **Container do monitor**: instância em execução da imagem, com hardening, healthcheck e o volume de estado montado em `/data`; no máximo um ativo.
- **Serviço systemd**: definição que cria, inicia, para e reinicia o container; habilitado para o boot; fonte dos logs no `journalctl`.
- **Volume de estado**: armazenamento persistente montado em `/data`, com estado dos itens, fila de eventos, estado do Teams, lock e marca do último ciclo; pertence ao UID 10001.
- **Arquivo `.env`**: configuração e segredos no host, fora da imagem e do repositório, com permissões restritas.
- **Verificação de deploy**: serviço do systemd disparado a cada 5 min que compara o commit da branch principal com o commit em execução e implanta o novo; registra o último commit implantado e o último commit com falha já avisado.
- **Credencial do GitLab**: token ou chave de deploy somente leitura, guardada na VM, fora do repositório e da imagem.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Em uma VM sem Docker, um operador que segue só o README consegue construir, instalar, subir, ver logs e ver o status de saúde da automação em até 30 minutos, sem usar nenhum comando Docker.
- **SC-002**: Após reboot da VM sem login, o monitor volta a executar ciclos em até 5 minutos após o fim do boot em 100% dos testes de reboot.
- **SC-003**: Após o processo do monitor ser morto ou falhar, o serviço volta a executar em até 2 minutos (30 s de espera mais o tempo de subida), e continua tentando enquanto a falha persistir.
- **SC-004**: Depois de recriar o container, atualizar a imagem ou reiniciar a VM, 100% dos arquivos de `/data` continuam presentes, nenhuma nova linha de base é criada e todos os eventos que estavam na fila são entregues.
- **SC-005**: A primeira execução numa VM nova estabelece a linha de base sem nenhum alerta de queda em massa.
- **SC-006**: 100% dos controles de hardening (raiz somente leitura, `/tmp` em tmpfs, zero capabilities, no-new-privileges, UID 10001) são confirmados por inspeção do container em execução.
- **SC-007**: Uma segunda instância sobre o mesmo volume é recusada em 100% das tentativas.
- **SC-008**: Ao parar o serviço, o encerramento termina em no máximo 30 s, sem perda de eventos (o que não foi enviado continua na fila).
- **SC-009**: O espaço ocupado pelo journal não passa de 55 MB (50 MB de teto mais 10% de tolerância), medido com `journalctl --disk-usage`, mesmo após dias de execução contínua.
- **SC-010**: Nenhuma busca nas camadas e metadados da imagem encontra valores do `.env`.
- **SC-011**: A suíte de testes automatizados passa sem alterações no código Python da automação.
- **SC-012**: Um commit novo na branch principal entra em execução na VM em até 15 minutos (5 min de verificação mais build e reinício), sem ação manual.
- **SC-013**: Em 100% das falhas de deploy, a versão anterior continua monitorando sem interrupção e exatamente um aviso de falha por commit chega ao canal operacional do Teams.

## Assumptions

- A VM de destino é Ubuntu Server 26 com systemd 259, acessada por SSH, com Podman 5.7.0 instalado pelos pacotes da distribuição ou por um repositório indicado no README.
- O serviço é de nível de sistema (controlado com `sudo systemctl`, não `systemctl --user`), o que atende ao requisito de subir no boot sem login.
- O monitor continua sem portas publicadas e sem rede especial: precisa apenas de saída HTTPS, como hoje. No build, a VM também precisa de saída HTTPS para baixar a imagem base e os pacotes Python.
- A operação continua com uma única VM e uma única instância; orquestração (Kubernetes, pods múltiplos) está fora do escopo.
- A versão com Docker roda só na máquina do desenvolvedor; a VM nunca teve Docker nem estado do monitor. Não há migração de volume, rollback para Docker nem desinstalação de Docker na VM.
- O `.env` da VM é criado a partir do mesmo modelo usado hoje (as variáveis não mudam).
- A constituição cita "contêiner Docker" em Restrições Adicionais; esta feature exige emenda PATCH (1.0.1) para "contêiner OCI executado com Podman", a ser feita junto com esta feature.
- O changelog do projeto registra a troca de runtime, como nas features anteriores.
- O repositório será migrado do GitHub para o GitLab da empresa antes da instalação na VM; a VM tem saída HTTPS (ou SSH) para esse GitLab. A migração do repositório em si está fora do escopo.
- Os testes não barram o deploy na VM: proteger a branch principal (merge só com testes passando, ex.: pipeline do GitLab) é prática recomendada no README, mas não faz parte desta feature.
- O aviso de deploy no Teams é emitido pelo mecanismo de deploy, fora do código Python da automação, que continua sem mudança de comportamento (FR-024).
- Execução em container na máquina do desenvolvedor (Windows) está fora do escopo: o README documenta só a VM Ubuntu com systemd. Localmente, o desenvolvimento usa Python e pytest no ambiente virtual, sem container, e o Docker deixa de ser suportado pelo repositório (FR-023).
