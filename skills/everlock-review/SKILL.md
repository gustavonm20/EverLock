---
name: everlock-review
description: Revisar alterações do EverLock buscando regressões de autorização, dados, biometria e interface, com evidências no diff e testes proporcionais. Use quando o pedido for revisar uma mudança; não modifica arquivos por si só.
---

# Revisar uma mudança do EverLock

Resolva checkout e comparação exata solicitada. Leia AGENTS.md e o diff completo
do escopo, seguindo os chamadores relevantes. Não inclua alterações de outra cópia
nem trate documentação antiga como prova do comportamento atual.

Priorize os limites específicos do produto:

- Autorização e sessão verificadas no backend, inclusive depois de trabalho demorado.
- Cadastro/aceite não acionam a trava; restart não reexecuta comandos pendentes.
- Migrações atômicas com dados antigos preservados e versão futura recusada.
- Vetores cifrados, sem imagens/tokens em logs, backups ou artefatos públicos.
- Revogação e retenção verificadas antes de nova atuação; relógio real separado.
- Respostas tardias e câmera encerradas ao trocar de sessão/página; UI não sugere
  que um serviço configurado foi testado com pessoas reais.
- Webhook e relatórios são canais de observação, nunca de autorização.

Para cada problema material, forneça localização, cenário que o demonstra,
impacto e correção sugerida. Distinga defeito confirmado de hipótese. Testes devem
validar comportamento, não apenas a presença de palavras no código.
Use o fluxo especializado de Codex Security quando uma auditoria de segurança
for solicitada; não transforme uma revisão comum em auditoria exaustiva.

Não implemente correções nem publique resultados em serviços externos sem pedido.
Se não houver achados, diga o que foi inspecionado e quais limites permaneceram.
