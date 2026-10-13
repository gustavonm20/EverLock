---
name: everlock-feature
description: Implementar uma melhoria solicitada no EverLock preservando arquitetura local, dados e regras da porta virtual. Use para desenvolvimento do EverLock, não para revisões sem pedido de alteração.
---

# Desenvolver no EverLock

Localize o checkout escolhido pelo usuário; não suponha que o ZIP, a branch principal
e outras cópias locais estejam sincronizados. Confira branch, alterações locais,
AGENTS.md e os trechos pertinentes de docs/status.md, planning.md e decisions.md.
Use o código como evidência de implementação, e o planejamento como intenção.

Defina um incremento verificável a partir do pedido. Mantenha FastAPI, SQLite e
HTML/CSS/JS, salvo necessidade demonstrada e decisão do usuário. Atualizações do
banco devem entrar nas migrações de database.py, com teste de upgrade que preserve
contas e registros. Não abra nem migre o banco pessoal apenas para testar código.

Separe cadastro facial, autenticação, autorização e atuação. Consentir ou cadastrar
nunca libera a porta. Relógio de sessão é real; relógio do laboratório é virtual.
Reinício/reconexão não repetem comandos. Falhas de avisos não decidem a autorização.
Preserve eliminação de vetores na revogação/expiração e use dados sintéticos nos testes.

Teste os caminhos alterados, incluindo a recusa correspondente quando a mudança
envolver autorização, consentimento ou comandos. Em mudanças visuais, confira
desktop/celular, teclado e resposta tardia após logout. Consulte docs/testes-interface.md.
Registre evidências e limites em docs/status.md; testes com motor falso não encerram
aceites humanos de câmera, precisão facial, nobreak ou entrega externa.

Conclua com implementado, verificado e pendente. Publicação só quando estiver no
pedido; a ativação desta skill não autoriza push, merge ou atualização externa.
