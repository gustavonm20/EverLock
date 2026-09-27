# Estado do projeto

Atualizado em 27 de setembro de 2026. Entrega 0.3 registrada no [PR #14](https://github.com/gustavonm20/EverLock/pull/14).

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
- [Planejamento no Notion](https://app.notion.com/p/3e7e2dde06ab81f68b2ece96ce4a61a2) com Kanban, prioridades e dependências.

**101 testes aprovados** na suíte local completa, incluindo cadastro pendente/aprovação, política de senha, senha longa sem truncamento, compatibilidade de contas anteriores, recuperação por terminal e separação entre nobreak e simulação. Ruff e a verificação de diferenças também passaram. Há um aviso de descontinuação do cliente HTTP de testes, já acompanhado na [issue #13](https://github.com/gustavonm20/EverLock/issues/13); não houve falha de teste.

A interface de contas e os temas foram conferidos em computador e celular (390 × 844), incluindo persistência do tema e ausência de rolagem horizontal. O cadastro, a confirmação de senha e as restrições visíveis do usuário comum também foram conferidos. O [CI do incremento completo passou no GitHub](https://github.com/gustavonm20/EverLock/actions/runs/36295870556).

A `main` está protegida por regra ativa: pull request obrigatório, testes de qualidade aprovados, base atualizada, discussões resolvidas e bloqueio de exclusão/force push. Não há exceções de bypass.

## Ponto de parada solicitado

Após cadastro, senha, documentação e proteção das branches, não iniciar outra etapa sem nova solicitação. Comandos e conectividade permanecem no backlog.

## Ainda não implementado

- Identidades biométricas separadas das contas e políticas de acesso por horário.
- Protocolo de comandos remotos com validade, idempotência e confirmação.
- Falhas de internet, rede local e dispositivo como cenários independentes.
- Cadastro e reconhecimento facial real.
- Detecção de apresentação e avaliação com imagens autorizadas.
- Consentimento, retenção e exclusão de dados biométricos.
- Notificações e relatórios opcionais por n8n.
- Empacotamento e roteiro final de apresentação.
- Driver e medições reais do nobreak; dependem de marca/modelo e sistema operacional.

## Escopo físico atualizado

O grupo comprará somente um nobreak pronto para sustentar o computador. Porta, trava e sensores continuam virtuais. Marca/modelo, valor e autonomia não foram informados. A leitura real permanece indisponível até existir integração compatível; a bateria didática não será usada como substituta dessas informações.

Consulte [roadmap.md](roadmap.md) para as etapas e critérios de conclusão.
