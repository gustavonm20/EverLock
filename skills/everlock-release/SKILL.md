---
name: everlock-release
description: Preparar uma entrega do EverLock com versão, validação, documentação e publicação rastreável. Use para preparar ou publicar uma versão do EverLock; publicar depende do pedido explícito para cada destino.
---

# Preparar entrega do EverLock

Identifique checkout, branch, base remota e alterações já pertencentes ao usuário.
Leia AGENTS.md, docs/status.md e as regras de publicação vigentes. Faça a entrega
no fluxo normal de PR; esta skill não autoriza force-push, reescrita de histórico
ou desativação de proteções.

Alinhe versão em pyproject.toml, src/everlock/__init__.py e textos atuais da UI.
Execute Ruff e testes proporcionais ao diff. Mudanças transversais de banco,
sessões ou infraestrutura justificam a suíte geral; navegador segue
docs/testes-interface.md. Registre resultado real, falhas e avisos conhecidos.
Não declare precisão biométrica, liveness ou segurança física por esses testes.

Antes de publicar, confira git diff e arquivos selecionados. Exclua dados locais,
chaves, everlock.env, rostos, vetores, backups, logs e capturas com dados pessoais.
ZIPs devem conter apenas arquivos versionados. Use commits curtos e descritivos
em PT-BR, preservando a autoria verdadeira.

Quando autorizado:

- GitHub: branch/PR, links de evidência, aguarde o resultado do CI necessário.
  Distingua branch publicada, PR em revisão e mudança integrada à main.
- Notion: use a skill instalada de especificação/implementação, busque a página
  existente e atualize apenas a entrega relevante. Preserve aceites pendentes.
- Figma: use as skills instaladas do Figma; mantenha design alinhado à versão
  entregue, com dados fictícios e identificação do que é apenas proposta visual.

Não simule uma atualização externa sem confirmação da ferramenta. Ao final,
informe links, versão, evidências e qualquer destino que ainda não foi atualizado.
