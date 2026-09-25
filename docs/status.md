# Estado do projeto

Atualizado em 24 de setembro de 2026.

## Entregue e verificado

- Aplicação local em Python, FastAPI e SQLite.
- Interface responsiva em português para celular e computador.
- Porta e trava virtuais com liberação temporária de três segundos.
- Entrada externa, fechamento, saída interna e chave manual simulada.
- Histórico persistente e recuperação segura após reinicialização.
- Indicação de conexão perdida e bloqueio dos controles no navegador.
- Contrato de API local, iniciador do Windows e configuração do VS Code.
- Testes automatizados das regras, API, concorrência, persistência e fronteira do prazo.

## Incremento em validação

- Energia em Wh: consumo normal/econômico/residual, pulso de liberação, perdas e recarga.
- Relógio único com pausa, aceleração e avanço manual.
- Bateria baixa/crítica, esgotamento e recuperação de dois segundos virtuais.
- Ações manuais disponíveis sem energia virtual; retorno sem abertura automática.
- Persistência do cenário, migração aditiva e reinício pausado.
- Temas claro/escuro com sol/lua e preferência salva no navegador.
- Planejamento por entregas, dependências e critérios em [planning.md](planning.md).

Verificação estática aprovada. Uma rodada intermediária passou em 72 testes; a rodada final deve incluir os acréscimos de consumo de atuação e recuperação. O resultado definitivo será registrado após a execução da automação do repositório e da verificação visual.

## Próximo objetivo

Contas, login, papéis, revogação e histórico administrativo. Sessões terão expiração pelo tempo real, independente do relógio da simulação.

## Ainda não implementado

- Contas, login, papéis e permissões.
- Cadastro, revogação e políticas de acesso.
- Protocolo de comandos remotos com validade, idempotência e confirmação.
- Falhas de internet, rede local e dispositivo como cenários independentes.
- Cadastro e reconhecimento facial real.
- Detecção de apresentação e avaliação com imagens autorizadas.
- Consentimento, retenção e exclusão de dados biométricos.
- Notificações e relatórios opcionais por n8n.
- Empacotamento e roteiro final de apresentação.

Consulte [roadmap.md](roadmap.md) para as etapas e critérios de conclusão.
