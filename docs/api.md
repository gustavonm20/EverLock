# API local do simulador

Base: `http://127.0.0.1:8000`. Porta e energia de laboratório são simuladas. `/api/ups` informa que o nobreak é externo e não monitorado. Execute apenas um processo do servidor. O contrato estruturado está em `/openapi.json`; esta versão dispensa páginas de documentação que carreguem recursos externos.

Salvo `/api/health` e as rotas públicas de preparação/cadastro/login/sessão, as consultas exigem cookie de sessão. Histórico e controles `/api/simulation/*` exigem administrador. Na rota local de ações, `key_entry` e `unlock` são testes administrativos; as demais ações estão disponíveis a contas ativas. A liberação comum usa o painel remoto; a entrada facial local usa cadastro consentido e desafio de giro. Falta de sessão retorna 401, falta de permissão retorna 403. Veja os endpoints de autenticação em [accounts.md](accounts.md).

| Método e caminho | Resposta / finalidade |
|---|---|
| `GET /api/health` | Identificação, versão, modo `simulation` e disponibilidade da aplicação |
| `GET /api/status` | Posição da porta, trava, prazo restante, revisão e recursos implementados |
| `GET /api/events?limit=20` | Últimos eventos, do mais recente para o mais antigo; limite entre 1 e 100 |
| `POST /api/actions` | Solicitação de uma ação ao controlador |
| `GET /api/communication` | Canal, última observação, idade, indicador de leitura antiga e últimos 20 comandos visíveis |
| `POST /api/commands` | Novo comando remoto simulado; 202 significa solicitado, sem confirmar atuação |
| `GET /api/commands/{uuid}` | Situação e transições de um comando; 404 se inexistente ou sem acesso |
| `POST /api/simulation/network` | Administrador configura internet, rede local e atraso simulados |
| `POST /api/simulation/power` | Cortar/restaurar a alimentação virtual com `mains_available` booleano |
| `POST /api/simulation/clock` | Pausar, alterar velocidade ou avançar um intervalo |
| `POST /api/simulation/power/config` | Configurar um cenário de energia; pausa o tempo e encerra liberações |
| `GET /api/ups` | Informação de equipamento externo sem monitoramento; sem observações reais nem controles |
| `GET /api/identities/policy` | Administrador: versão e texto do consentimento, limites de retenção |
| `GET/POST /api/identities` | Administrador: listar / cadastrar identidade com consentimento |
| `PATCH /api/identities/{id}` | Administrador: ativar/desativar e/ou trocar a janela de horário |
| `POST/DELETE /api/identities/{id}/enrollment` | Administrador: registrar / remover o cadastro **simulado** |
| `POST /api/identities/{id}/consent/revoke` | Administrador: revogar consentimento e apagar o cadastro |
| `DELETE /api/identities/{id}` | Administrador: excluir a identidade por completo |
| `GET /api/identities/events` | Administrador: últimos 50 eventos de identidades |
| `GET /api/auth/face/availability` | Público: o motor facial está disponível? (`available`, `reason`) |
| `GET /api/auth/face/me` | Logado: situação do rosto da própria conta e texto do termo de consentimento |
| `POST /api/auth/face/enroll` | Logado: `{password, consent: true, images: [3 a 5]}`; cadastra o rosto da própria conta (403 senha errada, 409 rosto já em outra conta, 422 fotos ruins) |
| `DELETE /api/auth/face` | Logado: remove o próprio rosto |
| `DELETE /api/auth/users/{id}/face` | Administrador: remove o rosto de uma conta |
| `POST /api/auth/face/challenge` | Público: sorteia o desafio de giro (`challenge_id`, `direction`, `instruction`) |
| `DELETE /api/auth/face/challenge/{challenge_id}` | Público: encerra o desafio identificado pelo token secreto, inclusive durante análise; idempotente, com as mesmas proteções de origem e JSON |
| `POST /api/auth/face/login` | Público: `{challenge_id, front, turned: [1 a 6]}`; inicia a sessão (cookie) se o rosto for reconhecido e o giro, cumprido. Recusas: 409 (`no_match` = *Face não cadastrada*, `no_faces_enrolled`, `liveness_failed`, `face_changed`, `ambiguous`, `challenge_expired`), 422 captura, 429 bloqueio, 503 motor indisponível |
| Ações que exigem sessão com senha | `POST /api/auth/invites`, `POST /api/auth/users` com `role: admin` e `PATCH /api/auth/users/{id}` com `role: admin` respondem 403 `{"code": "password_required"}` se a sessão foi aberta pelo rosto |
| `POST /api/auth/forgot-password` | Público: `{identifier}` (e-mail ou usuário); sempre 202 com a mesma mensagem; envia o link se houver conta apta (429 após 5 pedidos em 5 min) |
| `POST /api/auth/reset-password` | Público: `{token, password, confirm_password}`; troca a senha, encerra as sessões e consome o link (400 se inválido ou expirado) |
| `GET /api/events` | Administrador: histórico da porta e da energia. Filtros opcionais: `outcome`, `source`, `type`, `q` (texto no título, detalhe ou usuário), `since` e `until` (datas `AAAA-MM-DD`, dias locais, inclusive) e `limit` (1 a 100) |
| `GET /api/events/export.csv` | Administrador: os mesmos filtros, até 5.000 linhas (`limit`), em CSV para o Excel (UTF-8 com BOM, separador `;`, células que começam com `=`, `+`, `-` ou `@` recebem `'` na frente) |
| `GET /api/notifications/status` | Administrador: webhook configurado, destino (só host:porta), nível, assinatura, contadores e último erro |
| `POST /api/notifications/test` | Administrador: enfileira uma notificação de teste (ignora o nível mínimo) |
| `GET /api/faces/status` | Administrador: motor facial disponível, motivo se não, limites e número de amostras |
| `POST /api/identities/{id}/face` | Administrador: cadastro facial. Corpo `{"images": [base64 ou data URL JPEG/PNG, 3 a 5]}`; guarda só vetores cifrados |
| `POST /api/recognition/challenge` | Administrador: cria um desafio de giro de uso único, válido por 45 segundos e vinculado à sessão; substitui o anterior dessa sessão |
| `DELETE /api/recognition/challenge/{challenge_id}` | Administrador: encerra um desafio da própria sessão, mesmo durante a análise; idempotente, sem revelar desafios de outra sessão |
| `POST /api/recognition/verify` | Administrador: envia `challenge_id`, foto `front` e 1 a 6 fotos `turned`; confere o movimento, reconhece e, se autorizado, libera a trava (409 recusa, 422 captura, 429 bloqueio, 503 motor indisponível) |
| `POST /api/recognition/simulate` | Administrador: teste de reconhecimento simulado (`match` ou `no_match`) |

Corpo de uma ação:

```json
{"action": "unlock"}
```

Ações: `unlock` (liberar por três segundos), `end_release` (encerrar liberação), `open` (entrada externa), `close` (fechar), `exit` (saída interna) e `key_entry` (chave virtual).

Uma ação concluída retorna HTTP 200, `ok: true`, `message` e `state`. Uma ação incompatível com o estado retorna HTTP 409, `ok: false`, `code`, `message` e `state`. Payload inválido retorna 422; corpo que não seja JSON retorna 415. Isso vale para toda requisição que altera algo, **inclusive as sem corpo** (`POST`, `PATCH` e `DELETE` de identidades): envie sempre `Content-Type: application/json`, como faz a interface. Pedidos de mutação vindos de outra origem no navegador retornam 403.

Estados de `door.lock`:

- `engaged`: porta virtual fechada e trava engatada.
- `released`: liberação temporária ativa, com porta aberta ou fechada.
- `pending_close`: porta aberta e nenhuma liberação ativa; aguarda fechamento.

`door.secured` só é verdadeiro com porta fechada e trava engatada. `updated_at` indica o último salvamento; `observed_at` indica quando o servidor produziu a observação. `revision` aumenta a cada salvamento, inclusive pontos periódicos sem evento. O prazo usa tempo virtual alimentado pelo relógio monotônico; as datas UTC servem para apresentação e histórico.

## Energia e tempo

Exemplos de corpos, enviados separadamente:

```json
{"mains_available": false}
```

```json
{"paused": true}
```

```json
{"advance_seconds": 21600}
```

`/clock` aceita exatamente uma operação: `paused` booleano, `speed` entre 1, 60 e 600, ou `advance_seconds` maior que zero e até 86400. Avançar exige pausa; caso contrário, retorna 409 com `clock_not_paused`.

`/power/config` aceita `capacity_wh`, `initial_percent`, `normal_load_w`, `economy_load_w`, `standby_load_w`, `charge_power_w`, `efficiency` e `actuator_extra_w`. Valores padrão e interpretação estão em [energy.md](energy.md); limites e tipos constam em `/openapi.json`. A configuração preserva a posição da porta e o tempo acumulado, restaura a alimentação e prepara o dispositivo ligado.

`/status` inclui `power`, `simulation` e `device.status` (`online`, `powered_off` ou `recovering`). Com 5% ou menos sem alimentação, ações eletrônicas retornam 409 com `device_powered_off`; durante os dois segundos virtuais de recuperação, `device_recovering`. Saída interna, chave e fechamento continuam possíveis. O tempo estimado de bateria considera o pulso atual, sem antecipar liberações futuras.

Eventos novos têm `simulated_at`, em segundos virtuais, e `actor`, com a conta responsável quando aplicável. Eventos anteriores à migração mantêm os campos novos nulos. O horário UTC registra quando o evento foi salvo; vários eventos de um avanço longo podem compartilhar esse horário, mas preservam seus instantes virtuais.

Os eventos separam tipo, título, detalhe, origem (`system`, `manual`, `lab`, `remote` ou `recognition`), resultado (`success`, `denied` ou `info`) e data. `/api/actions` representa os controles locais do laboratório. `/api/commands` implementa o canal remoto simulado, mantendo a decisão final no controlador.

O navegador não repete automaticamente uma ação se a resposta se perder. Ele consulta o estado novamente. A liberação repetida enquanto há uma ativa é recusada, sem ampliar o prazo. A liberação não é restaurada quando o processo reinicia.

As proteções de origem e endereço local complementam a sessão; não substituem autorização. Pessoas ou programas com acesso aos arquivos do computador continuam fora da proteção fornecida pelo login. Não exponha esta implantação HTTP local à internet.

## Comandos e observações remotas

Exemplo de POST em `/api/commands` (gere um UUID novo e use a versão da observação recebida):

```json
{
  "command_id": "0f378e2a-f8f5-4bdc-a6e3-e64f365635a8",
  "action": "unlock",
  "expected_version": "10a093b7-56a3-4baa-a3e3-963b1b5ed135",
  "valid_for_seconds": 10
}
```

`action` aceita `unlock` e `lock`; prazo inteiro de 1 a 30 segundos reais. `door.version` é um UUID de controle de conflito; não equivale à revisão geral que também muda com a bateria. Uma conta ativa pode enviar e consultar seus comandos; administrador vê todos. Nenhum comando remoto impede saída interna.

A resposta traz `duplicate` e `command`, com `id`, `action`, `actor`, `status`, `code`, `message`, `requested_at`, `expires_at`, `finished_at`, `valid_for_seconds` e `transitions`. Datas são segundos UTC desde a época Unix. Cada transição tem `status` e `occurred_at`; o resultado público nunca inclui hash da sessão.

Estados: `requested` → `accepted` → `executed`, com saídas `failed` ou `expired`. Uma duplicata idêntica retorna 200 com o mesmo resultado; conteúdo conflitante retorna 409. Comando enviado sem canal é registrado como falho e retorna 409. Limites de envio retornam 429. Falhas posteriores são consultadas pelo GET, com códigos como `state_conflict`, `authorization_revoked`, `command_expired` e `restart_interrupted`.

Exemplo de cenário administrativo:

```json
{"internet_available": false, "lan_available": true, "delay_seconds": 15}
```

Flags devem ser booleanos; atraso finito entre 0 e 30 segundos reais. O atraso é aplicado aos novos comandos, sem deslocar prazos dos existentes. Interromper canal cancela pendentes imediatamente; não há retomada na reconexão.

`/api/communication` retorna `mode`, as duas flags, `device_available`, `delay_seconds`, `channel_available`, `reason`, `observation`, `observation_stale`, `observation_age_seconds` e `commands`. A observação contém `door`, `device` e `observed_at` ISO UTC; antes da primeira leitura pode ser nula. Durante falhas, preserva a última observação com indicação explícita de que não confirma o estado atual. Veja [regras e cenários](communication.md).

## Identidades e reconhecimento simulado

Todas as rotas exigem administrador (401 sem sessão, 403 para usuário comum). Corpo de um cadastro:

```json
{"label": "Aluno 01", "retention_days": 30, "days": [0, 1, 2, 3, 4],
 "start": "08:00", "end": "18:00", "consent": true, "consent_version": "2026-10-01"}
```

`consent` precisa ser `true` e `consent_version` deve ser a de `/api/identities/policy` (senão, 422 ou 409). `days` usa 0 = segunda a 6 = domingo; `end` aceita `24:00`. Campos extras retornam 422. Uma identidade tem `state` (`ready`, `not_enrolled`, `inactive` ou `revoked`), `consent`, `retention_days`, `expires_at`, `schedule` e `access_now` com a decisão atual. Não há imagens, vetores ou modelo na resposta pública da identidade; `face_samples` informa somente a quantidade de amostras.

Na verificação facial real, o servidor não mantém a trava global durante a leitura das imagens. Antes de atuar, revalida sessão, prazo, cancelamento, identidade e regras da porta. Uma tentativa em processamento não pode ser reutilizada; troca de página, aba ou sessão pede o cancelamento pela interface. Capturas recusadas por qualidade não são contadas como falhas de identificação. Todas as amostras aproveitadas no desafio precisam corresponder ao rosto inicial, inclusive as que ainda não atingiram o giro mínimo.

`POST /api/recognition/simulate` recebe `{"scenario": "match", "identity_id": 3}` ou `{"scenario": "no_match"}`. Responde sempre com `simulated: true`, `code`, `message` e `state`. Recusa retorna 409 com o motivo (`consent_revoked`, `identity_inactive`, `not_enrolled`, `outside_schedule`, `no_match`, `door_open`, `device_powered_off`, `already_released`); identidade inexistente, 404. Regras completas em [identities.md](identities.md).

## Nobreak real

`/api/ups` retorna `source: "external_equipment"`, `status: "not_monitored"`, `observation: null` e `controls_available: false`. O equipamento alimenta o computador e não será integrado ao software. A API nunca usa a bateria virtual para preencher leituras reais.

Não há coleta USB, driver nem endpoint para enviar comandos ao nobreak. O status deve ser consultado no próprio equipamento. A compatibilidade elétrica e a duração de backup serão verificadas com o computador real, fora da simulação.
