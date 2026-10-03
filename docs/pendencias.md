# Pendências em aberto

Itens que dependem de uma ação sua. Marque aqui o que for resolvendo e me avise.

## Resolvidas por decisão (02/10/2026)

| # | Assunto | Decisão |
|---|---|---|
| 4 | Botão "Liberar trava" do painel remoto | Continua sem exigir rosto: é comando de quem está logado. Ver [decisão 20](decisions.md) |
| 5 | Administradores e o login por rosto | Podem entrar pelo rosto, mas essa sessão não cria convites nem administradores. Ver [decisão 21](decisions.md) |

## Dependem de você

| # | Pendência | O que falta | Onde está explicado |
|---|---|---|---|
| 1 | Avaliação facial real | Preparar fotos autorizadas separadas entre cadastro e teste, preencher o manifesto e executar `scripts\avaliar_rostos.py` seguindo o protocolo; medir erros e latência antes de ajustar os limites (0,45 porta, 0,55 login). Conferir giro (0,15 / 0,22) na câmera real com `scripts\testar_rosto.py` | [avaliacao-facial.md](avaliacao-facial.md), [facial-recognition.md](facial-recognition.md) |
| 2 | E-mail real (confirmação de cadastro e recuperação de senha) | Criar a senha de app do Gmail, preencher `everlock.env` e **trocar a senha da conta de e-mail**, que foi compartilhada em conversa | [accounts.md](accounts.md#e-mail-de-confirmação) |
| 3 | Notificações no n8n | Criar o fluxo com o nó Webhook, preencher `EVERLOCK_WEBHOOK_URL` e `EVERLOCK_WEBHOOK_SECRET` e usar "Enviar notificação de teste" em Atividade | [notifications.md](notifications.md) |
| 6 | Cópia de segurança | Dar dois cliques em `backup.cmd` e guardar o arquivo `.elbak` e a senha fora do computador | [backup.md](backup.md) |
| 7 | Aceites do planejamento | Revisar consentimento registrado pela própria pessoa e pedir a outra pessoa para executar o roteiro integrado; a automação já valida as regras, não substitui o ensaio humano | [planning.md](planning.md), [cenarios-integrados.md](cenarios-integrados.md) |
