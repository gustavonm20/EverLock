# EverLock — Planejamento de execução

Porta, trava e sensores são virtuais. A única compra física prevista é um nobreak pronto para alimentar o computador, confirmada em 26/09/2026; custo, modelo e autonomia ainda estão indefinidos. O software não exige assinatura paga. Python é a escolha atual; Java continua sendo uma alternativa autorizada. Não há equipe, prazo ou orçamento presumidos.

## Quadro de trabalho

Colunas: **Backlog → A fazer → Em andamento → Em revisão → Concluído**.

Cada tarefa deve ter título, etapa, prioridade, ordem, dependências, critério de aceite, evidência e link da issue/PR. Uma tarefa só passa a Concluído quando código, testes e documentação estão disponíveis. Trabalho implementado com verificações pendentes fica Em revisão.

O [espaço central no Notion](https://app.notion.com/p/EverLock-3e8e2dde06ab809c893fcbd6a4958ff8) reúne o planejamento anterior e suas 18 tarefas, preservando os links. Inclui Kanban vinculado à mesma base, roadmap, guia do grupo, checklists de demonstração e decisões de arquitetura/nobreak. Este documento mantém o conteúdo versionado. Atualizações entre GitHub e Notion são manuais; não existe sincronização automática.

| Ordem | Entrega | Situação | Prioridade | Dependência | Critério de aceite |
|---|---|---|---|---|---|
| 1 | Base local, API e banco | Concluído | P0 | — | Instalação documentada, API e SQLite funcionando |
| 2 | Porta e acesso manual | Concluído | P0 | 1 | Liberação de 3 s não abre porta; saída e chave funcionam; reinício não repete abertura |
| 3 | Relógio e energia virtual | Concluído | P0 | 2 | Consumo, recarga, perdas, pulso de atuação e transições reproduzíveis; banco antigo migra sem perder dados |
| 4 | Tema claro/escuro | Concluído | P1 | 1 | Botão sol/lua acessível; preferência sobrevive ao recarregamento; celular e computador legíveis |
| 5 | Login e sessão local | Concluído | P0 | 3 | Primeiro administrador sem senha padrão; hash de senha; sessão expira no tempo real; logout revoga sessão |
| 6 | Usuários e permissões | Concluído | P0 | 5 | Cadastro público aguarda aprovação; API aplica papéis; último admin é preservado; revogação imediata |
| 7 | Histórico administrativo | Concluído | P0 | 6 | Login, mudanças e revogações têm autoria; senhas e tokens nunca aparecem nos registros |
| 8 | Protocolo de comandos | Concluído | P0 | 6 | Identificador, prazo, duplicatas, confirmação e conflito tratados no backend |
| 9 | Internet, rede e dispositivo | Concluído | P0 | 8 | Falhas independentes; leitura antiga identificada; comando vencido não executa ao reconectar |
| 10 | Consentimento e cadastro facial | Backlog | P0 | 6 | Identidade biométrica separada da conta; consentimento, exclusão e retenção definidos |
| 11 | Reconhecimento de imagens | Backlog | P0 | 10 | Detector, alinhamento e embeddings locais; resultados preparados separados; autorização verificada |
| 12 | Avaliação facial | Backlog | P1 | 11 | Imagens autorizadas de teste diferentes do cadastro; erros e limitações documentados |
| 13 | Testes integrados e cenários | Backlog | P0 | 9, 12 | Face, acesso, revogação, falhas e recuperação demonstrados sem alterar código |
| 14 | Manual e apresentação | Backlog | P0 | 13 | Outra pessoa reproduz a demonstração a partir do manual |
| 15 | n8n opcional | Backlog | P2 | 13 | Só alertas/relatórios; sem poder de autorização; falha não afeta o sistema |
| Paralela | Monitoramento do nobreak por software | Fora do escopo | — | Decisão de 28/09/2026 | Não instalar driver nem apresentar a bateria virtual como leitura física |
| Paralela | Validar alimentação pelo nobreak | Backlog | P0 | Equipamento e computador disponíveis | Registrar continuidade real e retorno de energia; sem integração ao aplicativo |

## Etapa de energia

Issue: [#1 — Motor de energia virtual](https://github.com/gustavonm20/EverLock/issues/1).

- [x] Integrar porta e energia ao mesmo relógio virtual.
- [x] Acrescentar pausa, velocidades 1×/60×/600× e avanço por intervalo.
- [x] Modelar carga em Wh, perdas, consumo normal/econômico/residual e recarga.
- [x] Adicionar pulso de consumo durante a liberação e recuperação em 2 segundos virtuais.
- [x] Manter saída interna, chave e fechamento manuais com dispositivo desligado.
- [x] Persistir o cenário e migrar o banco anterior.
- [x] Validar pulso e recuperação com testes e demonstração local.
- [x] Publicar a entrega em revisão no PR #14 e registrar o CI de energia aprovado.

As evidências do incremento completo, incluindo contas e cadastro, estão em [status.md](status.md).

## Contas e permissões implementadas

1. Criar tabelas de usuários e sessões com migração aditiva.
2. Criar o primeiro administrador pela tela local, sem credenciais predefinidas.
3. Guardar somente hash de senha e hash do identificador de sessão.
4. Aplicar autenticação e papéis no backend, com sessões baseadas no tempo real.
5. Permitir cadastro, desativação e mudança de senha; impedir perda do último administrador.
6. Registrar ações administrativas sem dados secretos.
7. Construir telas de entrada e administração, respeitando tema e tamanho de tela.
8. Testar acesso anônimo, usuário comum, administrador, expiração, revogação e origem da solicitação.
9. Oferecer cadastro com aprovação e senha de pelo menos 6 caracteres, maiúscula, minúscula, número e símbolo, sem máximo.

## Comunicação implementada no incremento 0.4

- [x] Registrar identificador, recebimento, execução, falha e expiração.
- [x] Evitar execução duplicada e rejeitar conflito com a versão da porta.
- [x] Revalidar a sessão antes da atuação e cancelar pendentes ao reiniciar.
- [x] Separar internet, rede local e energia, mantendo observações antigas identificadas.
- [x] Acrescentar painel remoto e cenários administrativos de atraso e interrupção.
- [x] Verificar as regras por testes e documentar a demonstração em [communication.md](communication.md).

A continuação foi autorizada após a entrega de cadastro, senha e proteção do GitHub. O próximo incremento é consentimento e cadastro facial. Em 28/09/2026, o grupo definiu que o nobreak alimentará o computador sem integração ao aplicativo; veja [ups.md](ups.md).

## Rotina da equipe

A IA implementa, documenta e executa verificações. A equipe revisa o resultado e informa exigências acadêmicas. Cada incremento deve apresentar o que mudou, como reproduzir e o que ainda falta. Imagens de pessoas só entram na etapa facial, com autorização.

Não criar prazos fictícios. Quando houver data de apresentação, distribuir o trabalho conforme dependências e reservar uma etapa para integração e correção. O Notion organiza o trabalho; o GitHub guarda código, testes e revisão.
