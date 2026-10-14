# Feature Specification: Histórico de Quedas e Retornos em Banco de Dados

**Feature Branch**: `002-historico-quedas-sqlserver`

**Created**: 2026-10-14

**Status**: Draft

**Input**: User description: "Registrar em um banco SQL Server já existente o histórico de quedas e
retornos de cada link/porta/site monitorado. Cada queda deve ter horário de início, horário de
retorno (nulo enquanto estiver aberta), duração e identificação do alvo (rede/link ou site) e de
qual evento originou o registro. O objetivo é permitir, futuramente, consultar quanto tempo, em um
período específico, o site ou a rede ficaram fora, para analisar formas de solucionar as quedas. Os
registros devem acompanhar as mesmas regras de notificação já existentes (um registro por queda, um
por retorno, sem duplicar em reinício do serviço). Os lembretes não devem ser armazenados no
servidor, apenas os registros de queda e retorno. Se o banco estiver indisponível, o monitoramento
e as notificações continuam funcionando e os eventos não gravados devem ser retomados depois."

## Contexto

Esta feature complementa a feature `001-cato-socket`. O monitor já detecta quedas e retornos de
links e sites e avisa o Teams. Os avisos, porém, não deixam um histórico consultável. A equipe de
infraestrutura precisa saber, para um período, quanto tempo cada site ou link ficou fora, para
identificar padrões e priorizar soluções (troca de operadora, link redundante etc.).

O histórico segue as **mesmas decisões** já tomadas para os avisos: só entra no histórico o que
gerou (ou geraria) aviso de queda ou de retorno. O banco é apenas registro; ele nunca decide nem
bloqueia avisos (Constituição, princípio VIII).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cada queda notificada vira um registro no histórico (Priority: P1)

Quando o monitor avisa uma queda de link ou de site, o histórico ganha um registro de queda
**aberto**, com o alvo, o horário de início da queda e o evento que o originou. Quando o monitor
avisa o retorno, o mesmo registro é **fechado** com o horário de retorno e a duração.

**Why this priority**: sem isso não há histórico. É o mínimo para qualquer análise futura.

**Independent Test**: simular uma queda de link que ultrapassa a tolerância e depois volta.
Verificar que existe exatamente um registro para o link, aberto após o aviso de queda e fechado
após o aviso de retorno, com início, retorno e duração iguais aos dos avisos.

**Acceptance Scenarios**:

1. **Given** um link online, **When** ele fica offline além da tolerância e o aviso de queda é
   gerado, **Then** existe um registro de queda aberto para esse link, com início igual ao "desde"
   do aviso, retorno vazio e referência ao evento de queda.
2. **Given** um registro de queda aberto, **When** o aviso de retorno é gerado, **Then** o registro
   é fechado com o horário de retorno e a duração iguais aos do aviso, e com referência ao evento de
   retorno.
3. **Given** um link que fica offline por menos que a tolerância, **When** ele volta, **Then**
   nenhum registro é criado.
4. **Given** um site que cai por inteiro, **When** o aviso de site offline é gerado, **Then** existe
   um registro de queda aberto para o **site**, e nenhum registro novo para os links cobertos por
   esse aviso.
5. **Given** um aviso de lembrete diário ou de saúde do monitor, **When** ele é gerado, **Then**
   nada é gravado no histórico.

---

### User Story 2 - O histórico não atrapalha o monitoramento e não perde registros (Priority: P1)

Se o banco estiver fora, lento ou recusar a gravação, o monitor continua consultando a Cato e
avisando o Teams normalmente. Os registros não gravados ficam guardados e são gravados, na ordem,
quando o banco voltar, inclusive depois de um reinício do serviço.

**Why this priority**: é uma regra inegociável da constituição (princípio VIII). Um histórico com
lacunas também perde valor para a análise.

**Independent Test**: com o banco inacessível, provocar uma queda e um retorno. Confirmar que os
dois avisos chegam ao Teams no prazo normal. Reiniciar o serviço, liberar o banco e confirmar que o
registro aparece completo, uma única vez.

**Acceptance Scenarios**:

1. **Given** o banco inacessível, **When** ocorre uma queda que ultrapassa a tolerância, **Then** o
   aviso ao Teams sai no mesmo prazo de quando o banco está disponível.
2. **Given** registros pendentes de gravação, **When** o banco volta a responder, **Then** os
   registros são gravados na ordem em que os eventos ocorreram, com os horários reais dos eventos.
3. **Given** registros pendentes, **When** o serviço é reiniciado antes de o banco voltar, **Then**
   nenhum registro pendente é perdido.
4. **Given** uma falha de gravação, **When** ela acontece, **Then** fica registrada no log do
   monitor e **não** gera aviso de queda de link ou site.

---

### User Story 3 - Sem duplicidade em reinícios e reenvios (Priority: P2)

Reiniciar o serviço, reenviar uma gravação que falhou no meio ou repetir uma tentativa nunca gera
registros duplicados nem fecha a queda errada.

**Why this priority**: duplicatas inflariam o tempo fora e invalidariam a análise.

**Independent Test**: interromper o serviço logo após uma gravação, sem confirmar o sucesso
localmente, e reiniciar. Verificar que o banco tem um único registro para aquele evento.

**Acceptance Scenarios**:

1. **Given** um evento já gravado no banco, **When** a mesma gravação é tentada de novo, **Then** o
   banco continua com um único registro para o evento.
2. **Given** uma queda aberta antes de um reinício, **When** o serviço volta e o retorno ocorre,
   **Then** o registro original é fechado, sem criar outro.

---

### User Story 4 - Consultar o tempo fora em um período (Priority: P3)

Uma pessoa da equipe consegue, a partir dos dados gravados, calcular quanto tempo um site ou link
ficou fora em um período (ex.: "setembro de 2026"), incluindo quedas que começaram antes ou
terminaram depois do período e quedas ainda abertas.

**Why this priority**: é o objetivo final, mas a ferramenta de consulta (relatório, painel) fica
para uma feature futura. Aqui garantimos que os dados permitem o cálculo.

**Independent Test**: com registros conhecidos no banco, executar a consulta de exemplo entregue
com a feature para um período e comparar o total com o cálculo manual.

**Acceptance Scenarios**:

1. **Given** uma queda de 10:00 a 12:00, **When** se consulta o período 11:00–13:00, **Then** o
   tempo fora contabilizado é de 1 hora.
2. **Given** uma queda ainda aberta, **When** se consulta um período que termina agora, **Then** o
   tempo fora conta até o fim do período.

---

### Edge Cases

- **Site que volta com links ainda offline**: o registro do site é fechado. Para cada link que
  continua offline, é aberto um registro de queda próprio, com o início de queda que o monitor já
  tem para o link e referência ao evento de retorno do site. Quando esse link voltar, o aviso de
  retorno do link fecha esse registro.
- **Link já com queda aberta quando o site inteiro cai**: o registro do link continua aberto e o
  site ganha o próprio registro. O link é fechado quando o seu retorno for comunicado (pelo aviso
  de retorno do link, ou pelo aviso de retorno do site, se ele voltar junto).
- **Links cobertos que voltam junto com o site**: não ganham registro próprio. O tempo fora deles
  está representado pelo registro do site.
- **Itens já offline na linha de base** (primeira execução, estado corrompido ou item novo):
  não geram registro de queda, porque não geram aviso de queda e o início real é desconhecido.
  O histórico segue estritamente os avisos. Se o retorno desses itens for avisado depois, ele cai
  no caso "retorno sem registro aberto correspondente", descrito abaixo.
- **Retorno sem registro aberto correspondente** (ex.: queda anterior à ativação desta feature ou
  item que já estava offline na linha de base):
  o retorno é gravado como registro fechado com o início de queda informado no aviso. Ele é marcado
  como "aberto sem evento de queda registrado".
- **Item removido da Cato com queda aberta**: o registro permanece aberto. A remoção é registrada
  no log do monitor, sem inventar horário de retorno.
- **Oscilação**: cada episódio que ultrapassa a tolerância gera seu próprio registro, como nos
  avisos.
- **Banco fora por muito tempo**: os registros pendentes se acumulam sem limite de descarte. O
  volume esperado é pequeno (dezenas de eventos por dia).
- **Relógio e fuso**: horários são gravados em UTC; a conversão para o horário de Brasília é feita
  na consulta ou exibição.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST criar um registro de queda **aberto** para cada aviso de queda de link
  (`LINK_OFFLINE`) e de site (`SITE_OFFLINE`) gerado pelo monitor.
- **FR-002**: O sistema MUST fechar o registro de queda aberto do mesmo alvo quando o aviso de
  retorno correspondente (`LINK_RETORNO` ou `SITE_RETORNO`) for gerado, preenchendo horário de
  retorno e duração.
- **FR-003**: Cada registro de queda MUST conter: tipo de alvo (site ou link), identificação do
  site (id e nome), identificação do link quando for o caso (id, nome e tipo LAN/WAN), horário de
  início da queda, horário de retorno (vazio enquanto aberto), duração (vazia enquanto aberto) e
  referência aos eventos que abriram e fecharam o registro.
- **FR-004**: O horário de início, o de retorno e a duração MUST ser exatamente os mesmos
  informados nos avisos ao Teams.
- **FR-005**: O sistema MUST guardar também cada evento de queda e de retorno como entrada própria,
  com identificador único do evento, tipo, horário de ocorrência e alvo, para auditoria.
- **FR-006**: O sistema MUST NOT gravar no histórico lembretes diários, avisos de saúde do monitor
  (falha e recuperação de acesso à Cato) nem o aviso de início do monitor.
- **FR-007**: Quedas que não ultrapassam a tolerância (e, portanto, não geram aviso) MUST NOT gerar
  registro.
- **FR-007a**: Itens que já estavam offline na linha de base (primeira execução, estado corrompido
  ou item novo) MUST NOT gerar registro de queda aberto.
- **FR-008**: A gravação de um mesmo evento MUST ser idempotente: repetir a gravação não cria
  registro duplicado nem altera um registro já fechado.
- **FR-009**: Falha, lentidão ou indisponibilidade do banco MUST NOT interromper o ciclo de
  monitoramento, atrasar o aviso ao Teams além do prazo atual nem alterar a decisão de avisar.
- **FR-010**: Eventos cuja gravação falhar MUST ficar pendentes de forma persistente (sobrevivendo
  a reinícios) e ser gravados depois, na ordem em que ocorreram.
- **FR-011**: A fila de gravação MUST ser independente da fila de envio ao Teams: um atraso em uma
  não pode travar a outra.
- **FR-012**: Falhas de gravação MUST aparecer no log estruturado do monitor (com motivo
  sanitizado, sem credenciais), e MUST NOT gerar aviso de queda de link ou site.
- **FR-013**: Os dados de acesso ao banco MUST vir da configuração do ambiente, tratados como
  segredo (mascarados nos logs, nunca versionados).
- **FR-014**: Se a configuração do banco estiver ausente, o monitor MUST funcionar normalmente sem
  o histórico, informando no log de início que o histórico está desativado.
- **FR-015**: A feature MUST entregar a definição da estrutura de dados do histórico como script
  versionado, para ser aplicada no banco existente pela equipe responsável.
- **FR-016**: A feature MUST entregar ao menos uma consulta de exemplo que calcula o tempo total
  fora por site e por link em um período informado, tratando quedas que cruzam os limites do
  período e quedas ainda abertas.
- **FR-017**: O monitor MUST ter, para o banco, apenas as permissões necessárias para inserir e
  atualizar os registros do histórico.

### Key Entities *(include if feature involves data)*

- **Registro de Queda**: um episódio de indisponibilidade comunicado de um alvo. Atributos: tipo
  de alvo (site/link), site (id, nome), link (id, nome, tipo) quando aplicável, início, retorno,
  duração, situação (aberto/fechado), evento de abertura, evento de fechamento.
- **Evento Registrado**: cópia histórica de um aviso de queda ou retorno. Atributos: identificador
  único do evento no monitor, tipo, horário de ocorrência, alvo, registro de queda relacionado.
  Relaciona-se com o Registro de Queda (um registro tem 1 evento de abertura e até 1 de fechamento).
- **Gravação Pendente**: evento ainda não confirmado no banco, mantido no estado local do monitor
  até a confirmação.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos avisos de queda e retorno de link ou site enviados ao Teams têm registro
  correspondente no histórico em até 1 intervalo de verificação após o banco estar disponível.
- **SC-002**: Com o banco indisponível, o prazo de entrega dos avisos ao Teams é o mesmo de quando
  o banco está disponível (até 1 intervalo + 1 min após o fim da tolerância).
- **SC-003**: Após reinícios e reenvios, 0 registros duplicados para um mesmo evento.
- **SC-004**: O tempo fora calculado pela consulta de exemplo para um período bate com o somatório
  das durações dos avisos do mesmo período, com diferença de no máximo 1 intervalo de verificação
  por queda.
- **SC-005**: Uma pessoa da equipe consegue responder "quanto tempo o site X ficou fora no mês Y"
  em menos de 5 minutos, usando a consulta de exemplo.
- **SC-006**: 0 eventos pendentes perdidos após o banco ficar indisponível por até 7 dias, com
  reinícios do serviço no meio.

## Assumptions

- O SQL Server já existe e é acessível pela VM do monitor. A equipe responsável cria um banco ou
  schema e um usuário com permissão mínima. O monitor não cria a estrutura sozinho.
- O histórico começa a partir da ativação da feature. Não há importação de quedas anteriores.
- A retenção é indefinida nesta versão. O volume esperado é pequeno (dezenas de sites e centenas de
  links, poucos eventos por dia).
- A ferramenta de análise (relatório, painel, BI) está fora do escopo; esta feature entrega os
  dados e a consulta de exemplo.
- Os nomes de sites e links são gravados como estão no momento do evento. Renomeações posteriores
  não alteram registros antigos; a identificação estável é o id.
- A fonte de verdade para a lógica de estado continua sendo o estado local do monitor
  (constituição, princípio I). O banco é apenas registro histórico.
