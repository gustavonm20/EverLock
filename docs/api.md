# API local do simulador

Base: `http://127.0.0.1:8000`. Todos os estados são simulados. Execute apenas um processo do servidor. O contrato estruturado está em `/openapi.json`; esta versão dispensa páginas de documentação que carreguem recursos externos.

| Método e caminho | Resposta / finalidade |
|---|---|
| `GET /api/health` | Identificação, versão, modo `simulation` e disponibilidade da aplicação |
| `GET /api/status` | Posição da porta, trava, prazo restante, revisão e recursos implementados |
| `GET /api/events?limit=20` | Últimos eventos, do mais recente para o mais antigo; limite entre 1 e 100 |
| `POST /api/actions` | Solicitação de uma ação ao controlador |
| `POST /api/simulation/power` | Cortar/restaurar a alimentação virtual com `mains_available` booleano |
| `POST /api/simulation/clock` | Pausar, alterar velocidade ou avançar um intervalo |
| `POST /api/simulation/power/config` | Configurar um cenário de energia; pausa o tempo e encerra liberações |

Corpo de uma ação:

```json
{"action": "unlock"}
```

Ações: `unlock` (liberar por três segundos), `end_release` (encerrar liberação), `open` (entrada externa), `close` (fechar), `exit` (saída interna) e `key_entry` (chave virtual).

Uma ação concluída retorna HTTP 200, `ok: true`, `message` e `state`. Uma ação incompatível com o estado retorna HTTP 409, `ok: false`, `code`, `message` e `state`. Payload inválido retorna 422; corpo que não seja JSON retorna 415. Pedidos de mutação vindos de outra origem no navegador retornam 403.

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

`/status` inclui `power`, `simulation` e `device.status` (`online`, `powered_off` ou `recovering`). Abaixo de 5% sem alimentação, ações eletrônicas retornam 409 com `device_powered_off`; durante os dois segundos virtuais de recuperação, `device_recovering`. Saída interna, chave e fechamento continuam possíveis. O tempo estimado de bateria considera o pulso atual, sem antecipar liberações futuras.

Eventos novos têm `simulated_at`, em segundos virtuais. Eventos anteriores à migração mantêm esse campo nulo. O horário UTC registra quando o evento foi salvo; vários eventos de um avanço longo podem compartilhar esse horário, mas preservam seus instantes virtuais.

Os eventos separam tipo, título, detalhe, origem (`system`, `manual` ou `lab`), resultado (`success`, `denied` ou `info`) e data. As rotas atuais operam um laboratório local; ainda não são o protocolo futuro de comandos remotos autenticados, com identificador, expiração e confirmação por dispositivo.

O navegador não repete automaticamente uma ação se a resposta se perder. Ele consulta o estado novamente. A liberação repetida enquanto há uma ativa é recusada, sem ampliar o prazo. A liberação não é restaurada quando o processo reinicia.

As proteções de origem e endereço local reduzem a exposição acidental. Elas não constituem autenticação: outros programas ou pessoas com acesso à sessão deste computador conseguem operar o simulador. Contas e permissões pertencem a uma etapa posterior.
