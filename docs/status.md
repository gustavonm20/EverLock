# Estado do projeto

Entrega 0.4: comandos e falhas de conexão. A base de contas e energia foi entregue no [PR #14](https://github.com/gustavonm20/EverLock/pull/14); marca e ajustes visuais, no [PR #16](https://github.com/gustavonm20/EverLock/pull/16).

## Entregue e verificado

- Aplicação local em Python, FastAPI e SQLite.
- Interface responsiva em português para celular e computador.
- Porta e trava virtuais com liberação temporária de três segundos.
- Entrada externa, fechamento, saída interna e chave manual simulada.
- Histórico persistente e recuperação segura após reinicialização.
- Indicação de conexão perdida e bloqueio dos controles no navegador.
- Contrato de API local, iniciador do Windows e configuração do VS Code.
- Testes automatizados das regras, API, concorrência, persistência e fronteira do prazo.

## Implementado no incremento 0.3

- Energia em Wh: consumo normal/econômico/residual, pulso de liberação, perdas e recarga.
- Relógio único com pausa, aceleração e avanço manual.
- Bateria baixa/crítica, esgotamento e recuperação de dois segundos virtuais.
- Ações manuais disponíveis sem energia virtual; retorno sem abertura automática.
- Persistência do cenário, migração aditiva e reinício pausado.
- Temas claro/escuro com sol/lua e preferência salva no navegador.
- Planejamento por entregas, dependências e critérios em [planning.md](planning.md).
- Login obrigatório, administrador inicial, papéis e cadastro com aprovação administrativa.
- Senha com mínimo de 6 caracteres, maiúscula, minúscula, número e símbolo; sem máximo.
- Sessões de oito horas reais, logout, troca de senha, revogação e recuperação local.
- Histórico com autoria, limite de tentativas e proteção do último administrador ativo.
- Contrato de observações do nobreak separado da bateria virtual; nenhum driver real instalado.
- [Planejamento no Notion](https://app.notion.com/p/EverLock-3e8e2dde06ab809c893fcbd6a4958ff8) centralizado com as 18 tarefas anteriores, Kanban, checklists e páginas de apoio.

**101 testes aprovados** na suíte local completa, incluindo cadastro pendente/aprovação, política de senha, senha longa sem truncamento, compatibilidade de contas anteriores, recuperação por terminal e separação entre nobreak e simulação. Ruff e a verificação de diferenças também passaram. Há um aviso de descontinuação do cliente HTTP de testes, já acompanhado na [issue #13](https://github.com/gustavonm20/EverLock/issues/13); não houve falha de teste.

A interface de contas e os temas foram conferidos em computador e celular (390 × 844), incluindo persistência do tema e ausência de rolagem horizontal. O cadastro, a confirmação de senha e as restrições visíveis do usuário comum também foram conferidos. O [CI do incremento completo passou no GitHub](https://github.com/gustavonm20/EverLock/actions/runs/36295870556).

A `main` está protegida por regra ativa: pull request obrigatório, testes de qualidade aprovados, base atualizada, discussões resolvidas e bloqueio de exclusão/force push. Não há exceções de bypass.

## Incremento 0.4

- Comandos identificados com prazo real, recebimento, resultado e histórico persistente.
- Duplicatas sem nova atuação; conflito com versão antiga da porta é rejeitado.
- Revalidação de sessão/conta antes de executar; limite de envios e acesso por proprietário.
- Internet, rede local e energia independentes; observação remota antiga fica identificada.
- Interrupção/reinício cancelam comandos pendentes; reconexão não reabre a porta.
- Gravação atômica do resultado, estado da porta e evento de atuação.
- Painel remoto em português e controles administrativos de atraso e falhas.

A suíte completa passou com **116 testes**, incluindo 15 cenários novos de comunicação. Ruff passou. O aviso já acompanhado na issue #13 continua restrito ao cliente HTTP de testes. O [roteiro da nova etapa](communication.md) separa claramente os segundos reais do comando dos segundos virtuais de liberação.

## Ainda não implementado

- Identidades biométricas separadas das contas e políticas de acesso por horário.
- Transporte remoto entre computadores e implantação compartilhada com HTTPS.
- Cadastro e reconhecimento facial real.
- Detecção de apresentação e avaliação com imagens autorizadas.
- Consentimento, retenção e exclusão de dados biométricos.
- Notificações e relatórios opcionais por n8n.
- Empacotamento e roteiro final de apresentação.
- Teste real de continuidade com o nobreak alimentando o computador; integração por software foi retirada do escopo.

## Escopo físico atualizado

O grupo comprará somente um nobreak pronto para sustentar o computador. Porta, trava e sensores continuam virtuais. Marca/modelo, valor e autonomia não foram informados. Conforme decisão de 28/09/2026, não haverá integração de leitura ou controle do nobreak. A seção Status Nobreak informa isso e mantém os cenários virtuais em uma área de testes recolhida.

## Ajustes de interface de 28/09/2026

- Login como primeira tela, mesmo sem contas; cadastro apenas por escolha explícita.
- Logo fornecida pelo grupo com fundo transparente e contraste para os dois temas.
- Entrada local identificada como reconhecimento facial, ainda sem coleta ou atuação biométrica; não há botão de liberação direta nessa área.
- Remoção do cartão duplicado Nobreak real e da consulta periódica de telemetria.
- Textos secundários de Sua conta reduzidos; títulos mantidos.
- A suíte continua com 116 testes aprovados após a atualização das permissões e do contrato informativo do nobreak.

Consulte [roadmap.md](roadmap.md) para as etapas e critérios de conclusão.
