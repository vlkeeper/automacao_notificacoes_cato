# Feature Specification: Monitoramento de Sockets Cato com Avisos no Teams

**Feature Branch**: `001-cato-socket`

**Created**: 2026-10-06

**Status**: Draft

**Input**: User description: "Monitorar todos os sockets cadastrados no ambiente Cato da empresa (conexões LAN e WAN de cada um) e notificar a equipe no Microsoft Teams sobre quedas, retornos e pendências, em linguagem clara para usuários sem conhecimento de redes."

## Contexto e Problema

Hoje o acompanhamento do estado dos sockets Cato (equipamentos de conexão dos sites) é feito por
e-mails de alerta. Essas mensagens são pouco claras para usuários sem conhecimento de redes, o que
dificulta entender rapidamente o que caiu, onde caiu e se há ação a tomar. O objetivo é tornar esse
monitoramento simples e visível, entregando avisos claros em um canal de uso diário (Microsoft
Teams), compreensíveis por usuários leigos.

## Clarifications

### Session 2026-10-06

- Q: Link que cai e volta várias vezes depois de avisado: cada episódio gera par de avisos ou há limite? → A: Cada episódio acima da tolerância gera aviso de queda e de retorno, sem limite adicional.
- Q: Qual critério define "site offline" quando o status do site e o dos links divergem? → A: O site está offline se qualquer um dos dois indicar queda (status do site desconectado OU todos os links inativos).
- Q: Os avisos devem mencionar (@) pessoas ou grupos no Teams? → A: Não; apenas mensagem no canal, sem menções.
- Q: Quando um item ausente da resposta é considerado removido? → A: Após 3 consultas bem-sucedidas consecutivas sem o item.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ser avisado quando um link ou site cair (Priority: P1)

Como integrante da equipe, quero receber no Teams um aviso quando um link ou site ficar offline,
para saber rapidamente que há um problema e onde ele está.

**Why this priority**: É o motivo de existir da solução; sem o aviso de queda não há valor entregue.

**Independent Test**: Simular um link passando de online para offline por mais tempo que a
tolerância e verificar que exatamente um aviso de queda chega ao canal do Teams; simular a queda de
todos os links de um site e verificar que chega um único aviso de "site offline".

**Acceptance Scenarios**:

1. **Given** um link online, **When** ele ficar offline por tempo igual ou superior à tolerância
   definida, **Then** um aviso de queda é enviado uma única vez.
2. **Given** um link que ficou offline por menos que a tolerância, **When** ele voltar a ficar
   online, **Then** nenhum aviso é enviado.
3. **Given** um site com todos os links inativos por tempo igual ou superior à tolerância, **When**
   a verificação ocorrer, **Then** é enviado um único aviso de "site offline", sem avisos
   individuais dos links desse site.
4. **Given** um site em que apenas um dos links caiu, **When** a tolerância for atingida, **Then**
   o aviso identifica "link offline", deixando claro que o site segue operando parcialmente.

---

### User Story 2 - Ser avisado quando a conexão voltar (Priority: P1)

Como integrante da equipe, quero ser avisado quando um link ou site voltar a funcionar, para saber
que o problema foi resolvido.

**Why this priority**: Sem o aviso de retorno, a equipe não sabe se o problema persiste e o canal
perde credibilidade.

**Independent Test**: Após uma queda notificada, simular o retorno do link e verificar que chega um
aviso de retorno com a duração da indisponibilidade; repetir com uma queda abaixo da tolerância e
verificar que nada é enviado.

**Acceptance Scenarios**:

1. **Given** um link com queda já notificada, **When** ele voltar a ficar online, **Then** um aviso
   de retorno é enviado informando também por quanto tempo ficou fora.
2. **Given** um link cuja queda nunca foi notificada, **When** ele voltar, **Then** nenhum aviso de
   retorno é enviado.
3. **Given** um site com queda notificada, **When** ele voltar com um dos links ainda inativo,
   **Then** o aviso de retorno do site informa que esse link continua offline, e o link segue sendo
   tratado como pendência.

---

### User Story 3 - Receber lembrete diário de pendências (Priority: P2)

Como integrante da equipe, quero um lembrete diário, até as 08:00, listando os links que continuam
offline e desde quando, para que quedas antigas não sejam esquecidas.

**Why this priority**: Complementa os avisos de evento; evita que quedas longas caiam no
esquecimento, mas o monitoramento já entrega valor sem ele.

**Independent Test**: Com links offline no horário do lembrete, verificar que um único lembrete é
enviado listando cada link e o início da queda; sem links offline, verificar que nada é enviado;
reiniciar o serviço após o envio e verificar que não há reenvio.

**Acceptance Scenarios**:

1. **Given** que há links offline no horário do lembrete (padrão 08:00), **When** o horário for
   atingido, **Then** um único lembrete diário é enviado com cada link inativo e o início da queda.
2. **Given** que não há links offline, **When** o horário do lembrete for atingido, **Then** nenhum
   lembrete é enviado.
3. **Given** que o serviço foi reiniciado após o lembrete do dia, **When** ele voltar a operar,
   **Then** o lembrete não é reenviado no mesmo dia.

---

### User Story 4 - Entender o aviso sem conhecimento técnico (Priority: P1)

Como usuário sem formação em redes, quero avisos em linguagem simples e padronizada, para entender
o que aconteceu sem consultar o console da Cato.

**Why this priority**: É o problema central a resolver em relação aos e-mails atuais; um aviso
incompreensível não gera ação.

**Independent Test**: Apresentar exemplos de cada tipo de aviso a usuários sem formação em redes e
medir se identificam site, link afetado e desde quando, sem ajuda.

**Acceptance Scenarios**:

1. **Given** qualquer aviso enviado, **When** um usuário o lê, **Then** encontra: nome do site,
   qual link (quando aplicável), tipo do evento (queda de link, queda de site, retorno de link, retorno de
   site, lembrete, falha do monitor, recuperação do monitor ou início do monitor), desde quando e há quanto tempo.
2. **Given** avisos de tipos diferentes, **When** exibidos no canal, **Then** são visual e
   textualmente distinguíveis entre si (título, indicador visual e cor/ícone próprios por tipo).
3. **Given** qualquer aviso, **When** exibe horários e nomes, **Then** os horários estão no fuso de
   Brasília e os nomes de sites e links aparecem exatamente como no portal da Cato.

---

### User Story 5 - Saber que o próprio monitor está funcionando (Priority: P2)

Como responsável pela solução, quero ser avisado se o monitor não conseguir consultar a Cato ou
parar de funcionar, para não confundir "sem alertas" com "tudo bem".

**Why this priority**: Garante a confiança no silêncio do canal; necessário para operação
contínua, mas depende das histórias P1 para ter sentido.

**Independent Test**: Simular falhas repetidas na consulta à Cato e verificar o aviso do monitor
(sem alteração do estado dos links) e o aviso de recuperação; interromper o monitor e verificar que
o mecanismo externo sinaliza a ausência de atividade.

**Acceptance Scenarios**:

1. **Given** que a consulta à Cato falha em 5 verificações consecutivas, **When** a quinta falha
   ocorrer, **Then** é enviado um aviso sobre o monitor (distinto dos avisos de link), sem alterar o
   estado dos links.
2. **Given** que o aviso de falha do monitor foi enviado, **When** a consulta voltar a funcionar,
   **Then** é enviado um aviso de recuperação do monitor, uma única vez.
3. **Given** que o monitor deixa de executar, **When** o sinal de atividade deixar de chegar dentro
   do prazo esperado, **Then** um mecanismo externo sinaliza a ausência de atividade.

---

### Edge Cases

- **Falha ou lentidão da API da Cato**: não é interpretada como queda; o estado de sites e links
  permanece inalterado e a contagem de tolerância não avança nem é reiniciada por esse motivo.
- **Resposta sem um site ou link esperado**: tratada como observação inválida daquele item, não
  como "offline".
- **Primeira execução, sem histórico (ou histórico ilegível)**: a situação atual é registrada como
  linha de base, sem disparar avisos de queda em massa; é enviado um único aviso informativo de
  início do monitor, com o resumo da linha de base (sites e links monitorados e quantos já estão
  offline). Itens já offline nesse momento passam a constar do lembrete diário.
- **Reinício do serviço durante uma queda em andamento**: não duplica avisos e não reinicia a
  contagem da tolerância (o "desde quando" original é preservado).
- **Falha ao enviar ao Teams**: o aviso fica pendente e é reenviado nas verificações seguintes, na
  ordem original, mantendo o horário real do evento no texto.
- **Link oscilando (cai e volta repetidamente)**: oscilações abaixo da tolerância não geram aviso;
  cada episódio que ultrapassa a tolerância gera um aviso de queda e, ao voltar, um de retorno, sem
  limite adicional de avisos (decisão confirmada em Clarifications).
- **Site que retorna enquanto um de seus links permanece inativo**: o link inativo continua sendo
  tratado como pendência (aviso de retorno do site o menciona, e ele aparece no lembrete diário).
- **Link que já estava notificado como offline quando o site inteiro cai**: o aviso de site offline
  substitui novos avisos individuais; nenhum aviso duplicado do link é emitido.
- **Novo site ou link cadastrado na Cato durante a operação**: passa a ser monitorado com sua
  situação atual como linha de base, sem aviso de queda imediato.
- **Site ou link removido da Cato**: só é considerado removido após 3 consultas bem-sucedidas
  consecutivas em que não aparece na resposta (antes disso, a ausência é observação inválida e o
  estado permanece inalterado). No caso de um link, a contagem só avança enquanto o site está
  conectado, pois um site desconectado pode legitimamente não listar seus links. Ao ser considerado removido, o item deixa de ser monitorado,
  sem aviso de retorno ou queda, e sai do lembrete diário; a remoção é registrada nos logs.
- **Link caído enquanto o site está em PENDENTE_OFFLINE**: o aviso do link é adiado até o site ser
  decidido; se o site for notificado como offline, o link fica coberto pelo aviso do site; se o site
  voltar antes, o link segue sua própria contagem de tolerância.
- **Monitor parado no horário do lembrete**: o lembrete do dia é enviado na primeira verificação
  bem-sucedida após o horário configurado, ainda no mesmo dia.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE detectar mudanças de estado (online/offline) de sites e de links LAN e
  WAN de todos os sockets cadastrados no ambiente Cato da empresa.
- **FR-002**: O sistema DEVE aguardar uma tolerância configurável (padrão de 3 minutos) antes de
  notificar uma queda, contada a partir do momento em que a queda foi observada pela primeira vez.
- **FR-003**: O sistema DEVE notificar a queda no máximo uma vez por episódio e o retorno somente se
  a queda foi notificada.
- **FR-004**: O sistema DEVE considerar um site offline quando a Cato o reportar como desconectado OU quando todos os seus links estiverem inativos (qualquer um dos critérios basta) e DEVE diferenciar link offline (parcial) de site offline (total) e suprimir
  avisos individuais de link quando o site inteiro estiver offline; ao retorno do site, DEVE
  reavaliar os links para não perder um que continue inativo.
- **FR-005**: O sistema DEVE enviar um lembrete diário, no horário configurado (padrão 08:00, fuso
  de Brasília), com os links inativos e o início de cada queda, apenas quando houver pendências e no
  máximo uma vez por dia.
- **FR-006**: O sistema DEVE entregar as notificações em um único canal do Microsoft Teams, em texto
  claro e padronizado, contendo os campos definidos na História 4, com cada tipo de evento visual e
  textualmente distinguível.
- **FR-007**: O sistema DEVE preservar seu estado entre reinícios (situação de cada item, início da
  queda, avisos enviados, avisos pendentes, data do último lembrete e contagem de falhas de
  consulta), evitando avisos duplicados e perda da contagem de tolerância.
- **FR-008**: O sistema NÃO DEVE alterar o estado de sites ou links quando a consulta à Cato falhar
  e DEVE avisar sobre o problema do monitor após 5 falhas consecutivas (no máximo uma vez por
  sequência de falhas), com aviso de recuperação quando a consulta normalizar.
- **FR-009**: O sistema DEVE reenviar avisos cuja entrega ao Teams falhar, sem perder o evento e
  preservando a ordem; um aviso só é considerado enviado após confirmação de entrega.
- **FR-010**: O sistema DEVE permitir configurar tolerância, horário do lembrete e intervalo de
  verificação sem alterar o código, validando os valores na inicialização (intervalo entre 30 e 120 s; tolerância entre 60 e 3600 s e
  não menor que o intervalo) e recusando-se a iniciar com configuração ausente ou inválida.
- **FR-011**: O sistema DEVE manter segredos (credenciais da Cato, endereço do canal do Teams,
  endereço do serviço de sinal de vida) fora do código e dos registros (logs).
- **FR-012**: O sistema DEVE emitir registros de funcionamento a cada verificação e um sinal de
  saúde/sinal de vida periódico, permitindo que um mecanismo externo detecte que o monitor parou.
- **FR-013**: O sistema DEVE acessar os dados da Cato somente para leitura.

### Tabela de Transições (por site ou link)

| Estado atual | Observação | Novo estado | Ação |
|--------------|------------|-------------|------|
| ONLINE | online | ONLINE | nenhuma |
| ONLINE | offline | PENDENTE_OFFLINE (registra início da queda) | nenhuma |
| PENDENTE_OFFLINE | offline, tempo < tolerância | PENDENTE_OFFLINE | nenhuma |
| PENDENTE_OFFLINE | offline, tempo ≥ tolerância | OFFLINE_NOTIFICADO | aviso de queda (link ou site; link suprimido se o site estiver offline) |
| PENDENTE_OFFLINE | online | ONLINE | nenhuma (oscilação abaixo da tolerância) |
| OFFLINE_NOTIFICADO | offline | OFFLINE_NOTIFICADO | nenhuma (incluído no lembrete diário) |
| OFFLINE_NOTIFICADO | online | ONLINE | aviso de retorno com duração da queda |
| qualquer | consulta falhou / item ausente na resposta | inalterado | nenhuma (conta falha de consulta) |

Links suprimidos por queda do site são marcados como cobertos pelo aviso do site: quando voltam
junto com o site, o retorno é comunicado pelo aviso de retorno do site; os que continuam inativos
são citados nele e permanecem como pendência.

A linha de base (primeira execução ou estado corrompido) não é uma transição de item: gera apenas o
aviso informativo de início do monitor.

### Key Entities *(include if feature involves data)*

- **Site**: local monitorado (identificado pelo nome do portal da Cato); possui um estado geral
  (ONLINE, PENDENTE_OFFLINE, OFFLINE_NOTIFICADO), início da queda e um ou mais links.
- **Link**: conexão LAN ou WAN de um site; possui nome, tipo, estado, início da queda e indicação
  de aviso já enviado (ou coberto pelo aviso do site).
- **Evento de notificação**: queda de link, queda de site, retorno de link, retorno de site, lembrete
  diário, falha do monitor, recuperação do monitor ou início do monitor; possui horário do evento, conteúdo e situação de
  entrega (pendente/enviado).
- **Situação do monitor**: contagem de falhas consecutivas de consulta, data do último lembrete
  enviado e momento da última verificação concluída.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% das quedas que superam a tolerância geram exatamente um aviso de queda, sem
  duplicatas.
- **SC-002**: O aviso chega ao Teams em até 1 intervalo de verificação mais 1 minuto após o fim da tolerância, em operação normal (no máximo 2 minutos com o intervalo padrão de 60 s).
- **SC-003**: Nenhuma indisponibilidade da API da Cato gera avisos falsos de queda (0 ocorrências).
- **SC-004**: Em teste com usuários sem formação em redes, pelo menos 90% identificam corretamente
  o site, o link afetado e o desde quando apenas lendo o aviso, sem acessar o console.
- **SC-005**: Uma queda total de site gera um único aviso, e não um por link.
- **SC-006**: Após reinício do serviço, nenhum aviso já enviado é repetido.
- **SC-007**: 100% dos avisos com falha de entrega ao Teams são entregues após o canal voltar a
  aceitar mensagens.
- **SC-008**: A parada do monitor é sinalizada pelo mecanismo externo em até 3 intervalos de
  verificação.

## Assumptions

- Os avisos atuais por e-mail permanecem como estão; esta solução é complementar e não os substitui
  no início.
- O destino das notificações é um único canal do Teams, definido na configuração.
- A solução tem acesso somente leitura aos dados da Cato.
- Um site é considerado offline quando a Cato o reporta como desconectado ou quando todos os seus
  links estão inativos; a mesma tolerância se aplica a sites e links.
- "Até as 08:00" significa que o lembrete é enviado na primeira verificação a partir do horário
  configurado (padrão 08:00, horário de Brasília); se o monitor estiver parado nesse horário, o
  lembrete sai assim que ele voltar, no mesmo dia.
- O intervalo de verificação padrão é curto o suficiente (ordem de 1 minuto) para cumprir o SC-002,
  com um valor mínimo validado na inicialização para não sobrecarregar a API da Cato. O intervalo
  máximo permitido é de 120 s; nesse extremo o SC-002 permite até 3 minutos após a tolerância (1 intervalo + 1 minuto).
- O mecanismo externo de detecção de parada é um serviço de sinal de vida ("heartbeat") que alerta
  o responsável quando os sinais deixam de chegar.
- O limite de 5 falhas consecutivas para o aviso do monitor segue a constituição do projeto.

## Out of Scope

- Notificações por WhatsApp/Meta ou outros canais.
- Menções (@) a pessoas ou grupos nos avisos do Teams.
- Ações automáticas de correção ou alteração de configurações na Cato.
- Painel/dashboard próprio.
- Monitoramento de métricas de desempenho (latência, perda de pacotes, consumo).

## Verificação de Conformidade com a Constituição (v2.0.0)

| Princípio | Conformidade na spec |
|-----------|----------------------|
| I. Resiliência de Estado | FR-007, SC-006; casos de borda de reinício e primeira execução (linha de base) |
| II. Falha de Observação Não É Evento Observado | FR-008, SC-003; item ausente tratado como observação inválida; aviso após 5 falhas + recuperação |
| III. Máquina de Estados Explícita | Tabela de Transições com estados nomeados; notificações só nascem de transições; horários em Brasília apenas para exibição e lembrete |
| IV. Anti-Fadiga de Alertas | FR-002 a FR-005, SC-005; supressão por site, reavaliação no retorno, oscilação silenciosa, lembrete 1x/dia |
| V. Rede Defensiva e Entrega Sem Perda | FR-009, SC-007; fila de pendentes ordenada; intervalo configurável com piso (FR-010) |
| VI. Segredos Isolados e Fail-Fast | FR-010, FR-011, FR-013 |
| VII. Observabilidade do Próprio Monitor | FR-012, SC-008; História 5 |

Nenhuma exceção identificada.
