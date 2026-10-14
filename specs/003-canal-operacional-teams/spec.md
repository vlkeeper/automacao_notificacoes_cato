# Feature Specification: Canal Operacional Separado no Teams

**Feature Branch**: `003-canal-operacional-teams`

**Created**: 2026-10-14

**Status**: Draft

**Input**: User description: "Separar os avisos do Teams em dois canais, cada um com seu próprio
webhook. O canal atual continua recebendo só os avisos de rede: queda e retorno de link e de site e
o lembrete diário. Um novo canal operacional, com outro webhook, passa a receber os avisos sobre a
saúde do próprio robô: falha e normalização do acesso à Cato, aviso de início do monitor e, quando
existir, falha e normalização da gravação no banco de dados. O heartbeat externo continua sendo só
um ping no serviço de monitoramento e não envia mensagem ao Teams. Cada canal deve ter sua própria
fila de envio e de reenvio, de modo que um canal fora do ar não atrase nem bloqueie o outro,
mantendo a ordem dos avisos dentro de cada canal e sem duplicar em reinícios. O novo webhook é um
segredo configurado no ambiente, como o atual."

## Contexto

Hoje o monitor (feature `001-cato-socket`) envia todos os avisos para um único canal do Teams. Os
avisos sobre o próprio robô (sem acesso à Cato, acesso normalizado, monitor iniciado) se misturam
aos avisos de rede, que são os que interessam a quem acompanha as quedas. Esta feature separa os
dois públicos: o canal de rede fica só com o que é sobre a rede, e a equipe que mantém o robô passa
a ter um canal operacional próprio.

A feature `002-historico-quedas-sqlserver` cria os avisos de falha e normalização da gravação no
banco. Eles também pertencem ao canal operacional.

## Clarifications

### Session 2026-10-14

- Q: O que acontece se o webhook operacional não estiver configurado? → A: O robô recusa iniciar
  (`exit 1`), como já ocorre com o webhook atual.
- Q: Se um dos canais ficar muito tempo sem aceitar mensagens, o robô deve avisar no outro canal?
  → A: Sim. Após 15 minutos contínuos sem entregar num canal, um aviso único vai para o outro canal
  ("CANAL DE REDE SEM ENTREGA" ou "CANAL OPERACIONAL SEM ENTREGA"), e um aviso de normalização
  quando voltar.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Avisos de rede e avisos do robô em canais diferentes (Priority: P1)

Quem acompanha a rede vê, no canal atual, só quedas, retornos e o lembrete diário. Quem mantém o
robô vê, no canal operacional, só os avisos sobre a saúde do robô.

**Why this priority**: é o objetivo da feature. Sozinha, ela já reduz o ruído no canal de rede.

**Independent Test**: com os dois webhooks configurados, provocar uma queda de link e uma
sequência de falhas de acesso à Cato. Verificar que o aviso de queda chega só ao canal de rede e o
aviso de falha de acesso chega só ao canal operacional.

**Acceptance Scenarios**:

1. **Given** os dois canais configurados, **When** é gerado um aviso de queda ou retorno de link ou
   site, ou o lembrete diário, **Then** ele é entregue só no canal de rede.
2. **Given** os dois canais configurados, **When** é gerado o aviso "MONITOR: SEM ACESSO À CATO" ou
   "ACESSO NORMALIZADO", **Then** ele é entregue só no canal operacional.
3. **Given** os dois canais configurados, **When** o monitor inicia e gera o aviso "MONITOR
   INICIADO", **Then** ele é entregue só no canal operacional.
4. **Given** o histórico em banco ativo (feature 002), **When** é gerado o aviso de falha ou de
   normalização da gravação no banco, **Then** ele é entregue só no canal operacional.
5. **Given** o monitor em funcionamento, **When** o heartbeat externo é enviado, **Then** nenhuma
   mensagem é enviada a nenhum canal do Teams por causa disso.

---

### User Story 2 - Um canal fora do ar não atrapalha o outro (Priority: P1)

Se o webhook de um canal falhar (fluxo desativado, erro do Teams, URL revogada), os avisos do outro
canal continuam sendo entregues no prazo normal. Os avisos do canal com falha ficam guardados e são
reenviados na ordem quando ele voltar.

**Why this priority**: sem isso, uma falha no canal operacional poderia segurar avisos de queda,
que são o objetivo do produto (constituição, princípio V).

**Independent Test**: tornar o webhook operacional inválido, provocar uma queda de link e uma
falha de acesso à Cato. Verificar que a queda chega ao canal de rede no prazo normal. Restaurar o
webhook operacional e verificar que o aviso de falha de acesso chega depois, uma única vez.

**Acceptance Scenarios**:

1. **Given** o canal operacional falhando, **When** ocorre uma queda de link, **Then** o aviso
   chega ao canal de rede no mesmo prazo de quando os dois canais estão saudáveis.
2. **Given** o canal de rede falhando, **When** ocorre uma falha de acesso à Cato, **Then** o aviso
   chega ao canal operacional sem esperar o canal de rede.
3. **Given** avisos pendentes em um canal, **When** o canal volta a aceitar mensagens, **Then** os
   avisos são entregues na ordem em que foram gerados, com o horário real do evento no texto.
4. **Given** avisos pendentes em qualquer canal, **When** o serviço é reiniciado, **Then** nenhum
   aviso é perdido e nenhum aviso já entregue é reenviado.
5. **Given** o canal de rede sem conseguir entregar há 15 minutos contínuos, **When** o limite é
   atingido, **Then** um único aviso "CANAL DE REDE SEM ENTREGA" chega ao canal operacional;
   **When** o canal de rede volta a entregar, **Then** um único aviso de normalização chega ao canal
   operacional.
6. **Given** o canal operacional sem conseguir entregar há 15 minutos contínuos, **When** o limite é
   atingido, **Then** um único aviso "CANAL OPERACIONAL SEM ENTREGA" chega ao canal de rede, com o
   aviso de normalização correspondente quando ele voltar.

---

### User Story 3 - Atualizar uma instalação existente sem perder avisos (Priority: P2)

Ao atualizar o robô numa instalação que já está rodando, os avisos que estavam na fila única
esperando envio são distribuídos para a fila do canal correto, sem perda e sem duplicidade.

**Why this priority**: a atualização acontece uma vez, mas uma perda nesse momento seria
silenciosa.

**Independent Test**: com avisos de rede e de saúde do robô pendentes na fila atual, atualizar o
robô e verificar que cada aviso é entregue uma vez, no canal correto e na ordem original dentro do
canal.

**Acceptance Scenarios**:

1. **Given** uma fila única com avisos de rede e do robô pendentes, **When** o robô atualizado
   inicia, **Then** cada aviso vai para a fila do seu canal, mantendo a ordem relativa original.
2. **Given** o estado já migrado, **When** o robô reinicia, **Then** nada é migrado de novo.

---

### Edge Cases

- **Webhook operacional não configurado ou inválido**: o robô recusa iniciar, como já acontece com
  o webhook atual: configuração inválida, `exit 1`, com o erro listado no log sem expor segredos.
  Atualizar uma instalação existente exige configurar o novo webhook antes.
- **Os dois webhooks com a mesma URL**: é aceito. As filas continuam separadas por tipo de aviso;
  na prática, tudo chega ao mesmo canal.
- **Ordem entre canais**: não é garantida. Um aviso do robô pode chegar antes de um aviso de rede
  gerado antes dele, e vice-versa. A ordem é garantida só dentro de cada canal.
- **Falha de acesso à Cato e canal operacional fora ao mesmo tempo**: o aviso fica pendente no
  canal operacional e é entregue quando o canal voltar. Se o canal operacional ficar 15 minutos
  sem entregar, o canal de rede recebe o aviso único "CANAL OPERACIONAL SEM ENTREGA".
- **Canal oscilando**: falhas que se resolvem antes de 15 minutos não geram aviso no outro canal;
  a contagem recomeça a cada entrega bem-sucedida no canal.
- **Os dois canais fora ao mesmo tempo**: cada aviso de "sem entrega" fica pendente na fila do
  outro canal e é entregue quando ele voltar, seguido da normalização se o canal original também
  já tiver voltado. A situação fica registrada no log.
- **Reinício durante a falha de um canal**: o início da falha e o fato de o aviso já ter sido
  enviado são preservados; o aviso não é repetido.
- **Lembrete diário**: continua no canal de rede, pois lista os itens de rede ainda fora.
- **Aviso "MONITOR INICIADO" com itens offline na linha de base**: vai para o canal operacional;
  os itens já offline continuam aparecendo no lembrete diário do canal de rede.
- **Atualização com fila corrompida ou ilegível**: segue a regra já existente de estado corrompido
  (nova linha de base com um único aviso de início).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST suportar dois destinos de aviso no Teams: canal de **rede** (o webhook
  atual) e canal **operacional** (um novo webhook).
- **FR-002**: Avisos de queda e retorno de link, queda e retorno de site e o lembrete diário MUST
  ser enviados só ao canal de rede.
- **FR-003**: Os avisos "MONITOR: SEM ACESSO À CATO", "ACESSO NORMALIZADO", "MONITOR INICIADO" e,
  quando a feature 002 existir, os avisos de falha e normalização da gravação no banco MUST ser
  enviados só ao canal operacional. A única exceção ao isolamento entre canais são os avisos de
  falha de entrega de um canal (FR-004a).
- **FR-004**: Todo novo tipo de aviso MUST ter seu canal definido explicitamente; não existe canal
  "padrão" implícito.
- **FR-004a**: Quando um canal ficar 15 minutos contínuos sem conseguir entregar (com avisos
  pendentes e tentativas falhando), o sistema MUST enfileirar no **outro** canal um único aviso
  ("CANAL DE REDE SEM ENTREGA" ou "CANAL OPERACIONAL SEM ENTREGA"), com o horário desde quando
  falha e quantos avisos estão pendentes. Quando o canal voltar a entregar, MUST enfileirar no outro
  canal um único aviso de normalização. Esses avisos MUST NOT se repetir na mesma sequência de falha
  e MUST sobreviver a reinícios sem duplicar.
- **FR-005**: O heartbeat externo MUST NOT enviar mensagens ao Teams; seu comportamento atual não
  muda.
- **FR-006**: Cada canal MUST ter sua própria fila persistida de envio e reenvio. Uma falha de envio
  em um canal MUST NOT atrasar nem bloquear a entrega no outro.
- **FR-007**: Dentro de cada canal, os avisos MUST ser entregues na ordem em que foram gerados,
  mantendo o comportamento atual de reenvio e de não descarte.
- **FR-008**: Um aviso entregue com sucesso MUST NOT ser reenviado após reinício, e um aviso
  pendente MUST NOT ser perdido.
- **FR-009**: O webhook operacional MUST ser configurado por variável de ambiente, tratado como
  segredo: validado como endereço seguro (https), mascarado nos logs e nunca versionado.
- **FR-009a**: O webhook operacional é obrigatório. Se estiver ausente ou inválido, o robô MUST
  encerrar na validação de configuração (`exit 1`), listando o erro junto com os demais, como já
  ocorre com o webhook atual.
- **FR-010**: Na primeira execução após a atualização, os avisos pendentes da fila única atual MUST
  ser movidos para a fila do canal correspondente ao seu tipo, preservando a ordem relativa, uma
  única vez.
- **FR-011**: Os logs de envio MUST indicar o canal de destino (rede ou operacional) sem expor a
  URL.
- **FR-012**: O texto e o formato dos avisos MUST permanecer os mesmos de hoje; só muda o destino.

### Key Entities *(include if feature involves data)*

- **Canal de Aviso**: destino de mensagens no Teams. Valores: rede, operacional. Cada um tem um
  webhook (segredo) e uma fila de envio.
- **Fila de Envio por Canal**: lista ordenada e persistida de avisos pendentes de um canal, com
  número de tentativas e último erro, como a fila atual.
- **Mapeamento Tipo → Canal**: regra fixa que define para qual canal vai cada tipo de aviso. Os
  avisos de "sem entrega" e normalização de um canal vão sempre para o outro canal.
- **Situação de Entrega do Canal**: por canal, desde quando as entregas falham e se o aviso de
  "sem entrega" já foi emitido. Persistida para sobreviver a reinícios.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos avisos de rede são entregues só no canal de rede, e 100% dos avisos de saúde
  do robô só no canal operacional.
- **SC-002**: Com um canal indisponível, o outro continua entregando avisos no prazo atual (até 1
  intervalo + 1 min após o fim da tolerância para quedas).
- **SC-003**: 0 avisos perdidos e 0 avisos duplicados após reinícios, falhas de canal e a
  atualização da instalação.
- **SC-004**: Após a mudança, o canal de rede não recebe nenhuma mensagem sobre a saúde do robô,
  exceto o aviso "CANAL OPERACIONAL SEM ENTREGA" e sua normalização.
- **SC-005**: Uma falha contínua de entrega em qualquer canal é comunicada no outro canal em até 15
  minutos + 1 intervalo de verificação.

## Assumptions

- A atualização das instalações existentes inclui preencher a nova variável no `.env` e no
  `.env.example` antes de subir a nova versão; a documentação de configuração (README e contrato de
  configuração) é atualizada junto.
- O novo canal e o fluxo de webhook no Teams são criados pela equipe, do mesmo jeito do canal
  atual (Workflows → "Post to a channel when a webhook request is received").
- A variável do webhook atual mantém o nome e passa a representar o canal de rede, para não exigir
  mudança nas instalações existentes além da nova variável.
- O alerta do serviço de heartbeat externo (quando o robô para de enviar pings) é configurado no
  próprio serviço; se a equipe quiser recebê-lo no canal operacional, isso é feito lá, fora do
  robô.
- O volume de avisos operacionais é baixo (poucos por dia), sem necessidade de agrupamento.
