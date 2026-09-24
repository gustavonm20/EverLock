# API local da primeira etapa

Base: `http://127.0.0.1:8000`. Todos os estados são simulados. Execute apenas um processo do servidor. O contrato estruturado está em `/openapi.json`; esta versão dispensa páginas de documentação que carreguem recursos externos.

| Método e caminho | Resposta / finalidade |
|---|---|
| `GET /api/health` | Identificação, versão, modo `simulation` e disponibilidade da aplicação |
| `GET /api/status` | Posição da porta, trava, prazo restante, revisão e recursos implementados |
| `GET /api/events?limit=20` | Últimos eventos, do mais recente para o mais antigo; limite entre 1 e 100 |
| `POST /api/actions` | Solicitação de uma ação ao controlador |

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

`door.secured` só é verdadeiro com porta fechada e trava engatada. `updated_at` indica a última alteração registrada; `observed_at` indica quando o servidor produziu a observação. `revision` aumenta a cada evento persistido e sobrevive a reinicializações. O prazo usa relógio monotônico; as datas UTC servem para apresentação e histórico.

Os eventos separam tipo, título, detalhe, origem (`system`, `manual` ou `lab`), resultado (`success`, `denied` ou `info`) e data. As rotas atuais operam um laboratório local; ainda não são o protocolo futuro de comandos remotos autenticados, com identificador, expiração e confirmação por dispositivo.

O navegador não repete automaticamente uma ação se a resposta se perder. Ele consulta o estado novamente. A liberação repetida enquanto há uma ativa é recusada, sem ampliar o prazo. A liberação não é restaurada quando o processo reinicia.

As proteções de origem e endereço local reduzem a exposição acidental. Elas não constituem autenticação: outros programas ou pessoas com acesso à sessão deste computador conseguem operar o simulador. Contas e permissões pertencem a uma etapa posterior.
