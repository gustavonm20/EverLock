# Notificações por webhook (n8n)

O EverLock pode avisar um fluxo do **n8n** (ou qualquer receptor HTTP) quando algo importante acontece: reconhecimento recusado, entrada recusada, falta de energia virtual e outros alertas. É opcional: **sem `EVERLOCK_WEBHOOK_URL`, nada é enviado**.

## O que é enviado e quando

Cada evento do laboratório (porta, energia, comandos, reconhecimento) e da auditoria (contas e identidades) passa por um filtro de gravidade:

| Gravidade | Exemplos |
|---|---|
| `critical` | `mains_lost` (falta de energia), `device_powered_off` |
| `warning` | `login_denied`, `login_face_denied`, `permission_denied`, `invite_rejected`, `recognition_denied`, `recognition_no_match`, `command_denied`, `action_denied`, qualquer evento com resultado *denied* ou *failed* |
| `info` | abrir/fechar a porta, liberar a trava, criar conta, cadastrar identidade etc. |

`EVERLOCK_WEBHOOK_LEVEL` define o mínimo: `warning` (padrão), `info` (tudo) ou `critical`.

Corpo da mensagem (`POST`, `application/json`):

```json
{
  "app": "EverLock", "version": "0.15.0", "id": "b0c1…", "type": "recognition_denied",
  "severity": "warning", "title": "Evento do laboratório",
  "detail": "Consulte o histórico local.",
  "source": "recognition", "outcome": "denied", "actor": null,
  "occurred_at": "2026-10-02T14:03:21.123456+00:00"
}
```

**Privacidade na versão 0.15:** a fila e o receptor recebem somente os metadados
técnicos acima. Nomes de usuário, apelidos, identificadores de identidade e detalhes
livres não são enviados; imagens e vetores também não. O histórico local preserva
seus detalhes e continua sendo a fonte de auditoria. Use apenas destino confiável.

## Configuração

1. No n8n, crie um fluxo com um nó **Webhook** (método `POST`, caminho `everlock`). Ative o fluxo e copie a **Production URL** (a *Test URL* só funciona enquanto você clica em "Listen for test event").
2. Copie `everlock.env.example` para `everlock.env` e preencha:
   ```
   EVERLOCK_WEBHOOK_URL=http://127.0.0.1:5678/webhook/everlock
   EVERLOCK_WEBHOOK_SECRET=um-texto-longo-e-aleatorio
   EVERLOCK_WEBHOOK_LEVEL=warning
   ```
3. Reinicie o EverLock. Em **Atividade > Notificações (n8n)** (administrador), clique em **Enviar notificação de teste**: o painel mostra enviadas, falhas, fila e o último erro.
4. No n8n, depois do Webhook, ligue um nó **IF** em `{{ $json.body.severity }}` e envie e-mail, Telegram ou Slack só para `warning` e `critical`.

## Assinatura

Com `EVERLOCK_WEBHOOK_SECRET`, cada mensagem leva:

- `X-EverLock-Timestamp`: segundos desde 1970;
- `X-EverLock-Signature`: `sha256=` + HMAC-SHA256 hexadecimal de `timestamp + "." + corpo`, com o segredo.

O receptor deve recalcular, comparar em tempo constante e **rejeitar timestamps com mais de uns 5 minutos** (impede repetir uma mensagem antiga). Cabeçalhos HTTP não diferenciam maiúsculas; o n8n os entrega em minúsculas (`x-everlock-signature`). Exemplo de conferência em Python (a mesma conta que os testes do EverLock usam):

```python
import hashlib, hmac

def valida(segredo: str, timestamp: str, corpo: bytes, assinatura: str) -> bool:
    esperado = "sha256=" + hmac.new(segredo.encode(), timestamp.encode() + b"." + corpo,
                                    hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura)
```

No n8n, ligue **Raw Body** no nó Webhook para ter o corpo exato e calcule o HMAC em um nó **Code** (módulo `crypto`). Esse trecho **não foi testado dentro do n8n**: use-o como ponto de partida. Sem assinatura, qualquer programa que conheça a URL pode forjar avisos; mantenha a URL em segredo e prefira sempre definir o segredo.

## Como o envio funciona (e o que não promete)

- **Em segundo plano.** O evento entra numa fila; uma thread entrega. A porta, o login e a API **nunca esperam** o webhook.
- **Tentativas.** Falhas de rede e respostas 408, 425, 429 e 5xx são repetidas após 1 s, 5 s e 30 s. Outras respostas (404, 401…) indicam erro de configuração e não são repetidas.
- **Fila persistente de 100.** `data/notificacoes.sqlite3` guarda pendências por até
  24 horas. Se estiver cheia, o novo aviso é recusado e contado em *descartadas*.
  Reiniciar preserva IDs e orçamento de tentativas, não cria novos avisos do histórico.
- **Sem redirecionamentos**, para um destino não desviar o envio. Prazo de 5 s por tentativa.
- **Transporte.** `http` é aceitável para o n8n no mesmo computador ou rede local. Para outro endereço, use `https`: o painel avisa quando o destino é `http` fora de rede privada.
- **Melhor esforço.** A gravação da fila é separada da transação do domínio:
  falha de disco pode perder um aviso, sem decidir a autorização. Se o receptor
  receber e o aplicativo encerrar antes de confirmar localmente, pode haver envio
  duplicado. O receptor deve deduplicar pelo campo `id`, além de validar a assinatura.
- Ao mudar URL ou segredo, pendências do destino anterior são descartadas; eventos
  expirados não são reenviados. Contadores de sucesso/falha são da execução atual.
- O backup do produto não inclui essa fila nem os logs. Restaurar o banco principal
  não restaura nem limpa uma fila já existente; mantenha o webhook desativado até
  conferir as pendências locais quando restaurar na mesma pasta de dados.
- Eventos de segurança já registrados na auditoria antes de a notificação ser ativada não são reenviados.
