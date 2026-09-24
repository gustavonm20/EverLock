# Segurança

## Versões apoiadas

Somente a versão mais recente da branch `main` recebe correções. O EverLock atual é um laboratório local e não deve ser exposto à rede ou usado para controlar acesso físico.

## Como relatar

Use **Security > Report a vulnerability** no GitHub. Não abra uma issue pública e não inclua credenciais, imagens faciais, templates biométricos ou dados pessoais em relatos.

## Limites atuais

A aplicação fica em `127.0.0.1` e possui proteções básicas de origem, mas ainda não implementa autenticação, autorização, criptografia de templates biométricos nem protocolo de comandos remotos. Esses itens fazem parte do roadmap antes de qualquer avaliação de implantação real.

O projeto não declara certificação, conformidade legal ou adequação a uma instalação física. A análise de obrigações da LGPD será documentada antes do uso de dados biométricos.
