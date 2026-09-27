# Como contribuir

O EverLock é desenvolvido em incrementos verificáveis. Antes de alterar o código, escolha ou abra uma issue e confirme o critério de aceite. Porta, trava e sensores continuam virtuais. A única aquisição física prevista é um nobreak pronto para alimentar o computador; consulte [o plano de integração](docs/ups.md).

## Fluxo sugerido

1. Crie uma branch curta a partir de `main`, como `feat/energia-virtual` ou `fix/prazo-liberacao`.
2. Faça uma mudança focada e acrescente testes que verifiquem o comportamento, quando aplicável.
3. Execute `python -m ruff check src tests scripts` e `python -m pytest -q`.
4. Abra um pull request vinculado à issue e descreva como reproduzir o resultado.

A branch `main` é protegida: mudanças entram por pull request, com a verificação **Testes e qualidade** aprovada e a branch atualizada. Discussões de revisão devem ser resolvidas. Exclusão e force push são bloqueados, sem exceção para administradores. Não é exigido um número mínimo de aprovações de outra pessoa; a revisão da equipe continua fazendo parte da rotina.

Não versione arquivos `.env*`, bancos da pasta `data`, imagens faciais, credenciais ou outros dados pessoais. Use somente imagens com autorização explícita nos futuros testes biométricos. Resultados preparados para demonstração devem ser identificados como simulados.

Python é a linguagem selecionada para o MVP. Java continua sendo uma opção arquitetural válida, mas misturar backends não faz parte do escopo atual. Dependências novas precisam ter licença compatível, manutenção ativa, benefício claro e alternativa gratuita.
