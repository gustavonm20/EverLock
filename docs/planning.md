# EverLock — Planejamento de execução

Projeto inteiramente em software, sem construção de fechadura, compra de componentes ou serviço pago obrigatório. Python é a escolha atual; Java continua sendo uma alternativa de arquitetura autorizada. Não há equipe, prazo ou orçamento presumidos.

## Quadro de trabalho

Colunas: **Backlog → A fazer → Em andamento → Em validação → Concluído**.

Cada tarefa deve ter título, etapa, prioridade, ordem, dependências, critério de aceite, evidência e link da issue/PR. Uma tarefa só passa a Concluído quando código, testes e documentação estão disponíveis. Trabalho implementado com testes pendentes fica Em validação.

No Notion, criar uma página **EverLock — Planejamento** e uma base de tarefas, com uma visualização de quadro agrupada por Status e outra tabela ordenada por Etapa e Prioridade. A conexão com o Notion é necessária para publicar essa estrutura; este documento mantém o conteúdo versionado.

| Ordem | Entrega | Situação inicial | Prioridade | Dependência | Critério de aceite |
|---|---|---|---|---|---|
| 1 | Base local, API e banco | Concluído | P0 | — | Instalação documentada, API e SQLite funcionando |
| 2 | Porta e acesso manual | Concluído | P0 | 1 | Liberação de 3 s não abre porta; saída e chave funcionam; reinício não repete abertura |
| 3 | Relógio e energia virtual | Em validação | P0 | 2 | Consumo, recarga, perdas, pulso de atuação e transições reproduzíveis; banco antigo migra sem perder dados |
| 4 | Tema claro/escuro | Em validação | P1 | 1 | Botão sol/lua acessível; preferência sobrevive ao recarregamento; celular e computador legíveis |
| 5 | Login e sessão local | A fazer | P0 | 3 | Primeiro administrador sem senha padrão; hash de senha; sessão expira no tempo real; logout revoga sessão |
| 6 | Usuários e permissões | A fazer | P0 | 5 | Admin cadastra e desativa usuários; API aplica papéis; último admin é preservado; revogação imediata |
| 7 | Histórico administrativo | A fazer | P0 | 6 | Login, mudanças e revogações têm autoria; senhas e tokens nunca aparecem nos registros |
| 8 | Protocolo de comandos | Backlog | P0 | 6 | Identificador, prazo, duplicatas, confirmação e conflito tratados no backend |
| 9 | Internet, rede e dispositivo | Backlog | P0 | 8 | Falhas independentes; leitura antiga identificada; comando vencido não executa ao reconectar |
| 10 | Consentimento e cadastro facial | Backlog | P0 | 6 | Identidade biométrica separada da conta; consentimento, exclusão e retenção definidos |
| 11 | Reconhecimento de imagens | Backlog | P0 | 10 | Detector, alinhamento e embeddings locais; resultados preparados separados; autorização verificada |
| 12 | Avaliação facial | Backlog | P1 | 11 | Imagens autorizadas de teste diferentes do cadastro; erros e limitações documentados |
| 13 | Testes integrados e cenários | Backlog | P0 | 9, 12 | Face, acesso, revogação, falhas e recuperação demonstrados sem alterar código |
| 14 | Manual e apresentação | Backlog | P0 | 13 | Outra pessoa reproduz a demonstração a partir do manual |
| 15 | n8n opcional | Backlog | P2 | 13 | Só alertas/relatórios; sem poder de autorização; falha não afeta o sistema |

## Etapa de energia

Issue: [#1 — Motor de energia virtual](https://github.com/gustavonm20/EverLock/issues/1).

- [x] Integrar porta e energia ao mesmo relógio virtual.
- [x] Acrescentar pausa, velocidades 1×/60×/600× e avanço por intervalo.
- [x] Modelar carga em Wh, perdas, consumo normal/econômico/residual e recarga.
- [x] Adicionar pulso de consumo durante a liberação e recuperação em 2 segundos virtuais.
- [x] Manter saída interna, chave e fechamento manuais com dispositivo desligado.
- [x] Persistir o cenário e migrar o banco anterior.
- [ ] Validar a versão final dos testes, incluindo pulso e recuperação.
- [ ] Publicar a entrega com evidências e atualizar o quadro.

Uma rodada intermediária passou em 72 testes. Os acréscimos posteriores precisam de nova rodada; não confundir esse resultado com validação da versão final.

## Próxima etapa: contas e permissões

1. Criar tabelas de usuários e sessões com migração aditiva.
2. Criar o primeiro administrador por configuração local, sem credenciais predefinidas.
3. Guardar somente hash de senha e hash do identificador de sessão.
4. Aplicar autenticação e papéis no backend, com sessões baseadas no tempo real.
5. Permitir cadastro, desativação e mudança de senha; impedir perda do último administrador.
6. Registrar ações administrativas sem dados secretos.
7. Construir telas de entrada e administração, respeitando tema e tamanho de tela.
8. Testar acesso anônimo, usuário comum, administrador, expiração, revogação e origem da solicitação.

## Rotina da equipe

A IA implementa, documenta e executa verificações. A equipe revisa o resultado e informa exigências acadêmicas. Cada incremento deve apresentar o que mudou, como reproduzir e o que ainda falta. Imagens de pessoas só entram na etapa facial, com autorização.

Não criar prazos fictícios. Quando houver data de apresentação, distribuir o trabalho conforme dependências e reservar uma etapa para integração e correção. O Notion organiza o trabalho; o GitHub guarda código, testes e revisão.
