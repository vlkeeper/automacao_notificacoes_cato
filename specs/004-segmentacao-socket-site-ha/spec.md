# Feature Specification: Aviso único por socket em sites HA

**Feature Branch**: `004-segmentacao-socket-site-ha`

**Created**: 2026-10-14

**Status**: Draft

**Input**: User description: "Em sites com mais de um socket (HA), quando um socket inteiro fica offline mas o site continua conectado pelo outro, o monitor deve enviar um único aviso "SOCKET OFFLINE" (identificando o socket primário ou secundário) em vez de um aviso "REDE OFFLINE" por porta/WAN daquele socket. O retorno do socket gera um único aviso "SOCKET ONLINE". Quedas de portas dos sockets individuais não devem ser avisadas enquanto o socket estiver offline. Quando o site inteiro está offline, continua valendo só o aviso "SITE OFFLINE". Sites sem HA não mudam."

## Clarifications

### Session 2026-10-14

- Q: Como o monitor decide que um socket está "offline"? → A: Pelo campo `device.connected = false` da Cato; se o campo não vier, considera offline quando todas as WANs do socket estão offline.
- Q: Site HA em "SITE OFFLINE" volta com só um socket; quais avisos? → A: "SITE DE VOLTA" e, em seguida, "SOCKET OFFLINE" para o socket que continua fora (o retorno dele gera "SOCKET DE VOLTA").
- Q: Socket offline aparece no lembrete diário "PENDÊNCIAS DO DIA"? → A: Sim, uma única linha por socket offline (primário/secundário), omitindo as portas desse socket.
- Q: O que acontece com quedas de porta já avisadas ("REDE OFFLINE") quando o socket inteiro cai e depois volta? → A: Continuam abertas e silenciadas enquanto o socket está fora. Quando o socket volta, a porta que voltou junto encerra a queda sem aviso, e a porta que segue fora continua aberta sem novo "REDE OFFLINE"; o retorno posterior dela gera "REDE DE VOLTA".
- Q: O aviso de retorno do socket se chama "SOCKET ONLINE" ou "SOCKET DE VOLTA"? → A: "SOCKET DE VOLTA", no padrão de "SITE DE VOLTA"/"REDE DE VOLTA" (formerly referred to as "SOCKET ONLINE").

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Um único aviso quando um socket inteiro cai (Priority: P1)

Como operador de rede, quando um dos sockets de um site em alta disponibilidade (HA) fica totalmente offline, mas o site segue conectado pelo outro socket, quero receber um único aviso "SOCKET OFFLINE" que diga qual socket (primário ou secundário) caiu, em vez de vários avisos "REDE OFFLINE" — um por porta/WAN daquele socket.

**Why this priority**: Hoje a queda de um socket gera uma enxurrada de avisos de porta, escondendo a causa real (o socket) e gerando ruído nos canais de notificação. Este é o valor central da feature.

**Independent Test**: Simular, em um site HA, um socket desconectado da Cato (`connected = false`) mantendo o outro conectado, e verificar que apenas um aviso "SOCKET OFFLINE" é emitido, identificando o socket, e nenhum aviso "REDE OFFLINE" das portas desse socket.

**Acceptance Scenarios**:

1. **Given** um site HA com sockets primário e secundário conectados, **When** o socket secundário fica desconectado da Cato e o primário permanece online, **Then** é enviado um único aviso "SOCKET OFFLINE" identificando o socket secundário e nenhum aviso "REDE OFFLINE" por porta desse socket.
2. **Given** o mesmo site, **When** o socket primário fica desconectado da Cato e o secundário permanece online, **Then** é enviado um único aviso "SOCKET OFFLINE" identificando o socket primário.
3. **Given** um socket já sinalizado como offline, **When** uma porta individual desse socket muda de estado (cai ou volta) enquanto o socket continua offline, **Then** nenhum aviso adicional de porta é enviado.

---

### User Story 2 - Aviso único quando o socket retorna (Priority: P1)

Como operador, quando o socket que estava offline volta, quero receber um único aviso "SOCKET DE VOLTA" identificando o socket, para saber que a redundância foi restabelecida.

**Why this priority**: Fecha o ciclo do aviso de queda; sem ele o operador não saberia que a redundância foi recuperada.

**Independent Test**: Após um "SOCKET OFFLINE", restaurar o socket e verificar que exatamente um aviso "SOCKET DE VOLTA" é emitido, sem avisos de retorno por porta.

**Acceptance Scenarios**:

1. **Given** um socket sinalizado como offline, **When** o socket volta a ficar conectado, **Then** é enviado um único aviso "SOCKET DE VOLTA" identificando o socket.
2. **Given** um socket que acabou de voltar, **When** o estado das portas se estabiliza, **Then** nenhum aviso adicional de porta é enviado para aquele retorno.

---

### User Story 3 - Site inteiro offline mantém apenas "SITE OFFLINE" (Priority: P2)

Como operador, quando o site inteiro fica offline (nenhum socket conectado), quero continuar recebendo apenas o aviso "SITE OFFLINE", sem avisos "SOCKET OFFLINE" nem avisos por porta.

**Why this priority**: Preserva o comportamento existente e evita duplicidade de avisos para o mesmo evento.

**Independent Test**: Derrubar ambos os sockets de um site HA e verificar que somente "SITE OFFLINE" é emitido.

**Acceptance Scenarios**:

1. **Given** um site HA com ambos os sockets conectados, **When** ambos ficam offline, **Then** apenas o aviso "SITE OFFLINE" é enviado.
2. **Given** um socket já avisado como "SOCKET OFFLINE", **When** o outro socket também cai e o site fica offline, **Then** o site passa a ser tratado como "SITE OFFLINE" sem avisos por porta.
3. **Given** um site HA em "SITE OFFLINE", **When** apenas um socket volta, **Then** são enviados "SITE DE VOLTA" e, em seguida, um único "SOCKET OFFLINE" para o socket que continua fora, sem avisos por porta.

---

### User Story 4 - Sites sem HA permanecem inalterados (Priority: P2)

Como operador, quero que sites com um único socket continuem com o comportamento atual de avisos, sem qualquer mudança.

**Why this priority**: Evita regressão no comportamento da maioria dos sites.

**Independent Test**: Derrubar uma porta/WAN em um site de socket único e verificar que o aviso "REDE OFFLINE" segue sendo emitido como antes.

**Acceptance Scenarios**:

1. **Given** um site com um único socket, **When** uma porta/WAN fica offline, **Then** o aviso "REDE OFFLINE" é enviado exatamente como antes.

---

### Edge Cases

- Apenas parte das portas de um socket cai (socket continua conectado): seguem os avisos de porta existentes, pois o socket não está inteiramente offline.
- Todas as WANs de um socket caem, mas a Cato ainda o informa como conectado (`connected = true`): o socket não é considerado offline e seguem os avisos de porta existentes.
- O socket está offline e, ao voltar, algumas portas dele permanecem offline: é enviado "SOCKET DE VOLTA". As portas ainda offline que não tinham queda avisada passam a ser avisadas individualmente ("REDE OFFLINE"), conforme as regras atuais. As que já tinham queda avisada seguem a regra de FR-003a.
- Uma porta já avisada como "REDE OFFLINE" antes da queda do socket: sua queda fica aberta e silenciada durante o "SOCKET OFFLINE" (FR-003a).
- Um socket cai e o outro, depois, também cai: o site passa a "SITE OFFLINE". No retorno parcial do site (um socket volta), são enviados "SITE DE VOLTA" e, em seguida, "SOCKET OFFLINE" para o socket que continua fora, sem avisos por porta. O retorno posterior desse socket gera "SOCKET DE VOLTA".
- Reinício do monitor com um socket offline: o estado "socket offline" não deve gerar aviso duplicado nem perder o aviso de retorno.
- Oscilação rápida (flapping) de um socket: não deve gerar avisos duplicados além do que as regras de confirmação já existentes permitem.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Em site com mais de um socket, o sistema MUST considerar um socket "offline" quando a Cato informa o socket como desconectado (`device.connected = false`) enquanto o site permanece conectado por outro socket. Se o campo `connected` não vier na resposta, o socket MUST ser considerado offline quando todas as suas WANs estão offline. O estado das portas LAN (incluindo "HA link") não entra nessa decisão.
- **FR-002**: Ao detectar um socket offline nessa condição, o sistema MUST enviar um único aviso "SOCKET OFFLINE" que identifique se o socket é o primário ou o secundário.
- **FR-003**: Enquanto um socket estiver offline, o sistema MUST NOT enviar avisos "REDE OFFLINE" nem avisos de retorno das portas individuais desse socket.
- **FR-003a**: Quedas de porta já avisadas ("REDE OFFLINE") antes do "SOCKET OFFLINE" MUST permanecer abertas, sem novos avisos, enquanto o socket estiver offline. No retorno do socket, cada uma dessas portas que voltou junto MUST ter a queda encerrada sem aviso. Cada uma que segue offline MUST manter a queda aberta, sem novo "REDE OFFLINE", e seu retorno posterior MUST gerar "REDE DE VOLTA".
- **FR-004**: Quando o socket offline voltar a ficar conectado, o sistema MUST enviar um único aviso "SOCKET DE VOLTA" identificando o socket.
- **FR-005**: Quando o site inteiro estiver offline, o sistema MUST enviar apenas o aviso "SITE OFFLINE", sem "SOCKET OFFLINE" nem avisos por porta.
- **FR-005a**: Quando um site HA sair de "SITE OFFLINE" com apenas um socket conectado, o sistema MUST enviar "SITE DE VOLTA" seguido de um único "SOCKET OFFLINE" para o socket que continua desconectado.
- **FR-006**: Sites com um único socket MUST manter exatamente o comportamento de avisos atual.
- **FR-007**: Avisos "SOCKET OFFLINE" e "SOCKET DE VOLTA" MUST seguir os mesmos canais de notificação e o mesmo registro de histórico de quedas aplicados aos demais avisos do monitor.
- **FR-007a**: O lembrete diário "PENDÊNCIAS DO DIA" MUST listar cada socket offline como uma única pendência, identificando se é o primário ou o secundário, e MUST NOT listar as portas/WANs desse socket.
- **FR-008**: O estado de socket offline MUST ser preservado entre reinícios do monitor, de modo a não duplicar avisos nem perder o aviso de retorno.

### Key Entities

- **Site**: local monitorado, podendo ter um ou mais sockets (HA).
- **Socket**: equipamento do site, identificado como primário ou secundário; possui um conjunto de portas/WANs.
- **Porta/WAN**: link individual de um socket cujo estado gera avisos de rede.
- **Aviso**: notificação enviada ao operador (SOCKET OFFLINE, SOCKET DE VOLTA, REDE OFFLINE, SITE OFFLINE).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Na queda total de um socket em site HA com o outro conectado, o operador recebe exatamente 1 aviso (em vez de 1 por porta/WAN), em 100% dos casos testados.
- **SC-002**: No retorno do socket, o operador recebe exatamente 1 aviso "SOCKET DE VOLTA", em 100% dos casos testados.
- **SC-003**: Em queda total do site, o operador recebe apenas "SITE OFFLINE", sem avisos de socket ou de porta.
- **SC-004**: Sites sem HA apresentam avisos idênticos aos de antes da mudança em todos os cenários de regressão testados.
- **SC-004a**: Com um socket offline, o lembrete diário mostra exatamente 1 pendência para esse socket e nenhuma pendência para as portas dele.
- **SC-005**: O operador identifica qual socket (primário/secundário) caiu apenas lendo o aviso, sem consultar outra fonte.

## Assumptions

- A identificação de primário/secundário já existe no monitor (rotulagem por socket já implementada em feature anterior).
- "Socket offline" é determinado pelo campo `device.connected` da Cato (com reserva em "todas as WANs offline"; ver FR-001), usando as mesmas regras de confirmação já aplicadas aos demais avisos.
- Os avisos de socket usam os mesmos canais de Teams e o mesmo histórico de quedas já existentes.
- Sites HA com mais de dois sockets não fazem parte do escopo; considera-se o par primário/secundário.
