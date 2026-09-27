# Segurança

## Versões apoiadas

Somente a versão mais recente da branch `main` recebe correções. O EverLock atual é um laboratório local e não deve ser exposto à rede ou usado para controlar acesso físico.

## Como relatar

Use **Security > Report a vulnerability** no GitHub. Não abra uma issue pública e não inclua credenciais, imagens faciais, templates biométricos ou dados pessoais em relatos.

## Limites atuais

A aplicação fica em `127.0.0.1`, com sessão local, papéis, senhas com hash scrypt, revogação, limite de tentativas e proteções de origem. Consulte [contas e permissões](docs/accounts.md). Nenhuma credencial padrão é distribuída. O acesso aos arquivos do computador continua sendo uma fronteira de confiança; backups do SQLite contêm dados de contas e devem ser protegidos.

HTTPS, implantação remota, criptografia de futuros templates biométricos e protocolo de comandos com expiração ainda exigem etapas próprias. A autenticação local não torna esta versão apropriada para exposição pública.

O futuro nobreak alimentará o computador. Sua integração de leitura é separada da simulação: valores desconhecidos ficam indisponíveis, dados antigos são identificados e não há controle de tomadas ou desligamento real pela API. Os botões de energia do laboratório nunca devem comandar o equipamento ou o sistema operacional.

O projeto não declara certificação, conformidade legal ou adequação a uma instalação física. A análise de obrigações da LGPD será documentada antes do uso de dados biométricos.

## Proteção do repositório

A regra ativa da `main` exige pull request, verificação **Testes e qualidade** aprovada sobre a base atualizada e resolução das discussões de revisão. Ela impede exclusão e force push, sem lista de exceções. Essas regras protegem o fluxo de mudanças; não substituem a revisão do código e os controles da aplicação.
