# Comandos e falhas de conexão

Esta etapa simula um canal remoto dentro da aplicação local. Não cria um serviço em nuvem nem corta a internet do computador. O painel local mostra o estado interno do laboratório; o painel remoto mostra a última observação recebida pelo canal simulado.

## Regras de execução

- Cada comando tem UUID, ação `unlock` ou `lock`, versão esperada da porta e validade de 1 a 30 segundos reais (padrão: 10).
- O servidor registra `requested` (solicitado), o dispositivo virtual registra `accepted` (recebido) e a decisão termina em `executed`, `failed` ou `expired`.
- HTTP 202 confirma o registro da solicitação. Somente `executed` confirma que o controlador realizou a ação virtual naquele instante; a porta pode mudar depois.
- O mesmo identificador, usuário e conteúdo devolvem o resultado existente, sem repetir a ação. Alterar o conteúdo ou o proprietário mantendo o identificador retorna 409.
- Antes da atuação, a sessão e a autorização são verificadas novamente. Logout, expiração, desativação ou troca de senha impedem um comando pendente de executar.
- A versão da porta muda quando sua posição ou liberação muda. Um comando baseado em leitura anterior falha com `state_conflict`. Atualizações apenas da bateria não invalidam a versão.
- Porta aberta impede comandos remotos de travamento e liberação. Travar não fecha a porta e nunca bloqueia a saída interna.
- Há limite de 20 novos comandos por usuário por minuto de calendário e de 10 pendentes no processo. Duplicatas não consomem novos registros. O limite por minuto é proteção didática; alterações do relógio do sistema podem afetá-lo.

A validade e o atraso usam o relógio monotônico real, que mede intervalos sem depender do calendário. Pausar ou acelerar a simulação não altera esses prazos. Já os três segundos de liberação da trava usam o relógio **virtual**. As datas de expiração apresentadas no histórico são projeções de calendário; a decisão usa o intervalo monotônico.

## Perdas e recuperação

| Cenário | Efeito no canal remoto | Controles locais |
|---|---|---|
| Internet simulada cortada | Pendentes falham; última leitura fica antiga | Continuam disponíveis conforme energia |
| Rede local simulada cortada | Mesmo cancelamento, com motivo próprio | Continuam disponíveis conforme energia |
| Dispositivo virtual sem energia ou recuperando | Não atua; observação fica antiga | Saída, chave e fechamento manuais continuam |
| Atraso maior ou igual ao prazo | Comando expira antes de atuar | Sem alteração por esse comando |
| Servidor real inacessível | Navegador bloqueia controles remotos e identifica leitura antiga | O navegador não garante operação sem servidor |
| Reinício do processo | Solicitações incompletas falham; liberações antigas não retornam | Estado recuperado e relógio virtual pausado |

O canal não guarda uma fila para executar após reconexão. Interrupções cancelam os pendentes; comandos enviados já sem conexão são registrados como falhos. Reconectar só atualiza a observação. Para atuar, é necessário um novo comando, com nova identificação e leitura atual.

Se a resposta HTTP se perder, a interface consulta o histórico; não repete automaticamente o POST. O botão administrativo de repetição usa o mesmo identificador para demonstrar a prevenção de duplicatas.

Internet, rede local e disponibilidade do dispositivo têm campos separados. A observação remota inclui data, idade em segundos reais e indicador `observation_stale`. O estado da porta só vem dessa observação, sem substituir uma leitura antiga pela verdade interna da tela local.

## Persistência e organização

`communication.py` controla entrega, prazos, observações e consulta do histórico. `controller.py` decide a atuação. `remote_commands` guarda solicitação e resultado; `command_transitions` guarda mudanças de situação; `network_state` guarda o cenário de rede. A migração é aditiva.

A decisão final do comando, o estado da porta e o evento de atuação são gravados na mesma transação SQLite. O recebimento é salvo antes. Se o processo cair entre recebimento e execução, o comando incompleto falha no próximo início, sem retomada. O UUID de versão da porta muda a cada inicialização; prazos monotônicos não são reconstruídos após reinício.

O hash da sessão fica restrito ao banco, nunca aparece no payload público. Usuários consultam seus próprios comandos; administradores consultam os últimos 20 de todas as contas. Eventos de atuação têm origem `remote` e autoria. Todos os registros ficam locais; ainda não há política automática de limpeza do histórico.

## Demonstração reproduzível

1. Entre como administrador, mantenha a porta fechada e pause o relógio virtual para facilitar a observação.
2. Em **Conexão**, deixe internet e rede local disponíveis e atraso zero. Clique em **Liberar trava**. Confira Solicitado → Recebido → Executado; a porta continua fechada, com a trava liberada.
3. Expanda os cenários de rede e repita o último envio. O identificador e o resultado se mantêm; não há novo evento de liberação.
4. Clique em **Engatar trava**. A trava engata. A saída interna continua funcionando; feche a porta localmente depois.
5. Configure atraso de 15 segundos e prazo de 5 segundos. Envie uma liberação e aguarde pelo menos 5 segundos reais. O histórico mostra Expirado, sem liberar a trava.
6. Com atraso de 15 segundos e prazo de 30, envie outro comando e corte a internet simulada antes de 15 segundos. O comando falha. Use saída/fechamento locais e observe que a leitura remota permanece antiga.
7. Restaure a internet. A leitura atualiza, mas o comando anterior não executa. Repita o cenário cortando somente a rede local.
8. Configure energia inicial em 5%, corte a alimentação virtual e observe o dispositivo sem operação. Saída e chave virtuais permanecem possíveis. Restaure a alimentação e avance 2 segundos virtuais: não há repetição de comandos.
9. Para testar reinício, envie com atraso de 30 segundos e pare/reabra o servidor antes da entrega. Faça login novamente; o histórico deve informar interrupção pelo reinício.

Esses resultados comprovam as regras do simulador. Reconhecimento facial, transporte entre máquinas e medições do nobreak exigem etapas próprias.
