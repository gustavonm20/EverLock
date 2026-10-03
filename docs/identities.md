# Identidades, consentimento e reconhecimento

As identidades representam quem pode liberar a trava virtual: consentimento, retenção, ativação e horários são aplicados no servidor. Há cadastro simulado e cadastro facial com OpenCV. O cadastro facial guarda apenas vetores cifrados; imagens ficam na memória durante a análise. Veja [facial-recognition.md](facial-recognition.md).

## O que existe e o que não existe

| Existe | Ainda não existe |
|---|---|
| Identidades separadas das contas de acesso | Medição de precisão com imagens autorizadas do grupo |
| Termo versionado, revogação, exclusão e retenção | Consentimento da identidade dado pela própria pessoa (hoje o administrador o registra) |
| Janela de horário por dia da semana | Prova de vida robusta |
| Cadastro facial, vetores cifrados e desafio de movimento | |
| Cadastro **simulado** e teste de reconhecimento **simulado** | |

No cadastro simulado, `enrollment = simulated` é apenas um marcador sem dado biométrico. No cadastro facial, `face_templates` guarda vetores cifrados e a identidade informa `enrollment = face`. Nenhuma tabela guarda imagens. `GET /api/status` informa `capabilities.face_recognition` conforme a disponibilidade do motor e do cofre; `identities: true` indica o gerenciamento das identidades.

## Identidade não é conta

Contas (`users`) autenticam quem opera o laboratório. Identidades (`identities`) representam pessoas reconhecíveis pela câmera da porta. As tabelas não se referenciam: desativar ou excluir uma conta não altera identidades, e uma identidade não tem senha, papel nem sessão. Somente administradores gerenciam identidades e executam os testes. O rosto opcional para entrar numa conta vive em `account_faces`, separado do cadastro da porta.

O campo `label` é um **apelido ou código** (2 a 40 caracteres: letras, números, espaço, ponto, hífen ou apóstrofo), não um nome completo. É único sem diferenciar maiúsculas de minúsculas.

## Consentimento

O texto e a versão atual (`2026-10-01`) vêm de `GET /api/identities/policy`. Para cadastrar, o administrador confirma que a pessoa foi informada e concordou; a API exige `consent: true` e a versão vigente do texto. Se o texto mudar enquanto a tela está aberta, o cadastro é recusado (409) até que ela seja recarregada. São registrados: versão, quem registrou e quando. O termo anterior (`2026-09-29`) não cobria vetores faciais: uma identidade antiga precisa ser recriada com o termo vigente antes do cadastro facial.

- **Revogar** (`POST /api/identities/{id}/consent/revoke`) apaga o marcador simulado e os vetores faciais e bloqueia novas liberações. A identidade fica marcada como revogada, não pode ser reativada nem receber novo cadastro e só pode ser excluída. Para voltar a participar, é preciso excluir e cadastrar de novo, com novo consentimento.
- **Excluir** (`DELETE /api/identities/{id}`) remove apelido, consentimento, cadastro e horários.

## Retenção

Cada identidade nasce com um prazo de 1 a 365 dias (padrão: 30), contado a partir do consentimento. Ao vencer, ela é **excluída por completo**, não apenas bloqueada. A verificação ocorre ao iniciar o servidor e em cada consulta, cadastro ou teste. O prazo não muda depois do cadastro, pois alteraria os termos aceitos.

## Horário de acesso

A janela tem dias da semana (0 = segunda … 6 = domingo), início e fim no formato `HH:MM`, usando o **horário local do computador**. Ela vale de `início` (inclusive) até `fim` (exclusivo). `24:00` só é aceito como fim e representa o dia inteiro (`00:00` a `24:00`).

Se o início for depois do fim (por exemplo, 22:00 a 06:00), a janela atravessa a meia-noite, e a parte da madrugada pertence ao dia em que a janela **começou**. Assim, sexta 22:00 a sábado 06:00 é uma única janela de sexta.

O relógio é o de calendário do servidor, independente do relógio virtual da simulação: pausar ou acelerar a porta não muda o horário permitido.

## Ordem da decisão

`evaluate()` (função pura em `identities.py`) responde na ordem abaixo e para na primeira recusa:

| Ordem | Código | Significado |
|---|---|---|
| 1 | `consent_revoked` | Consentimento revogado |
| 2 | `retention_expired` | Prazo de retenção vencido (na prática a identidade já foi excluída) |
| 3 | `identity_inactive` | Identidade desativada pelo administrador |
| 4 | `not_enrolled` | Sem cadastro simulado nem vetores faciais |
| 5 | `outside_schedule` | Fora da janela de horário |
| 6 | `authorized` | Autorizada neste horário |

## Teste de reconhecimento simulado

`POST /api/recognition/simulate` (administrador) recebe `{"scenario": "match", "identity_id": 3}` ou `{"scenario": "no_match"}`. Não usa câmera nem imagem, e toda resposta traz `simulated: true`. Ele **não** produz nota de confiança: seria um número inventado.

1. `no_match` registra o evento e recusa (409, `no_match`); a trava não muda.
2. `match` consulta a decisão acima. Recusas viram evento `recognition_denied` (409) com o motivo.
3. Se autorizada, o controlador aplica as mesmas condições do canal remoto: dispositivo ligado e **porta fechada** (`device_powered_off`, `device_recovering`, `door_open`). Só então libera a trava por três segundos virtuais.

Como em todo o projeto, **liberar a trava não abre a porta**: depois disso ainda é preciso usar "Abrir / entrar". Uma segunda tentativa durante a liberação é recusada (`already_released`) sem ampliar o prazo. Saída interna, chave e fechamento continuam disponíveis em qualquer cenário.

Os eventos usam origem `recognition`, registram o administrador que executou o teste e citam apenas `Identidade #n`.

## Privacidade da auditoria

Eventos da porta, auditoria de identidades e histórico de contas citam somente o **número** da identidade, nunca o apelido. Os números não são reutilizados (`AUTOINCREMENT`), então "Identidade #4" nunca passa a apontar para outra pessoa. Assim, excluir uma identidade remove tudo o que a identificava; permanecem apenas o número, o autor e a data da exclusão. Um teste procura o apelido em todos os históricos após a exclusão.

## Como demonstrar

1. Entre como administrador e abra **Identidades**.
2. Leia o termo, informe um apelido (ex.: `Aluno 01`), escolha o horário e marque a confirmação. Cadastre.
3. Clique em **Registrar cadastro simulado**, depois em **Simular reconhecimento**. A trava fica Liberada por três segundos virtuais e a porta continua fechada.
4. Repita durante a liberação: recusa com `already_released`. Use **Simular rosto desconhecido**: recusa sem alterar a trava.
5. Desative a identidade ou mude o horário para outro dia e repita: a recusa informa o motivo.
6. **Revogue o consentimento**: o cadastro é apagado e o teste passa a ser recusado. Depois **exclua** a identidade e confira em *Histórico de identidades* que só o número aparece.

## Reconhecimento facial e avaliação

O pipeline OpenCV produz um candidato depois de um desafio de movimento; `evaluate()` continua decidindo a autorização antes da liberação. Os vetores são cifrados e apagados ao revogar, excluir ou vencer a retenção. A [avaliação facial](avaliacao-facial.md) usa imagens autorizadas distintas do cadastro, sem alterar limites automaticamente. Medição real e consentimento da identidade pela própria pessoa continuam pendentes.
