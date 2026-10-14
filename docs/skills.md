# Trabalhar no EverLock com as skills

Skills são instruções reutilizáveis para o Codex: ajudam a manter as regras do
projeto em cada entrega. Não são funções executadas pelo EverLock, não exigem um
servidor e não substituem testes, revisão ou permissão para publicar.

## As três skills do projeto

| Skill | Para que serve | Exemplo de pedido no Codex |
|---|---|---|
| `everlock-feature` | Implementar um incremento, preservando dados, arquitetura e limites da porta virtual | `$everlock-feature Melhore o filtro de atividade; preserve os dados e valide os caminhos alterados.` |
| `everlock-review` | Revisar um diff, explicar defeitos e riscos com evidências | `$everlock-review Revise a branch atual; não altere nem publique arquivos.` |
| `everlock-release` | Conferir versão, testes, documentação e preparar uma entrega rastreável | `$everlock-release Prepare a entrega e atualize o GitHub e o Notion. Não atualize o Figma nesta entrega.` |

As três foram instaladas no Codex deste computador. Para usá-las, abra o projeto
no Codex e envie um dos pedidos acima. O nome iniciado por `$` pede explicitamente
a skill; o Codex também pode selecioná-la quando o pedido corresponder à descrição.
Se acabou de instalar e ela não aparece, inicie uma nova conversa e confira a lista
de skills. Não é preciso ativá-las dentro do VS Code ou iniciar o EverLock para isso.

Os conectores de GitHub, Notion e Figma são separados: precisam estar conectados à
conta e ter acesso ao destino. Uma skill não cria acesso nem garante que a conexão
está funcionando. Solicite cada publicação no próprio pedido.

## Instalar em outro computador

O código-fonte das instruções está em `skills/`, neste repositório. Peça ao Codex:
“Instale as três skills desta pasta no meu Codex, sem sobrescrever versões locais
sem conferi-las.” A instalação copia cada pasta para o diretório de skills do
Codex, normalmente `%USERPROFILE%\.codex\skills`. Antes de instalar, revise o
`SKILL.md`; instruções de terceiros não devem receber permissões desnecessárias.

## Um ciclo de trabalho simples

1. Escolha uma melhoria e descreva o resultado desejado, o que não deve mudar e
   como saber que ficou pronto. Use `everlock-feature`.
2. Confira a implementação e peça `everlock-review` sobre a branch/diff exato.
3. Teste a jornada no aplicativo. Diga o que observou; testes com dados fictícios
   não substituem os aceites com câmera, pessoas ou nobreak.
4. Use `everlock-release` e diga quais destinos devem ser atualizados. A entrega
   segue branch/PR e as proteções existentes; não reescreve o histórico.

Exemplo completo: “Use $everlock-feature para melhorar [resultado]. Preserve
[regras]. Considere pronto quando [critério verificável]. Primeiro inspecione o
código atual. Ao terminar, informe implementado, verificado e pendente. Não
publique ainda.”

As integrações não sincronizam os três serviços continuamente. Cada atualização
precisa de evidência e autorização; n8n continua opcional, fora da autorização e
do processamento biométrico. Consulte também [AGENTS.md](../AGENTS.md).

Referências oficiais: [criar skills](https://developers.openai.com/plugins/build/skills)
e [testar ativação explícita no Codex](https://developers.openai.com/blog/eval-skills).
