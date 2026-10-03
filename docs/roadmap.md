# Etapas de desenvolvimento

O trabalho será executado em incrementos pela IA, com implementação, testes, correções e documentação em cada etapa. A equipe avalia os resultados, informa exigências acadêmicas e, quando necessário, fornece imagens autorizadas.

## Situação atual

A base, porta, energia, tema, contas e permissões estão entregues. O incremento 0.4 acrescenta comandos com prazo real, confirmação e falhas de conexão simuladas, com validação em [status.md](status.md). O incremento 0.11 entregou filtros e exportação do histórico e o roteiro de apresentação ([roteiro-apresentacao.md](roteiro-apresentacao.md)). O incremento 0.8 entregou as notificações por webhook para o n8n ([notifications.md](notifications.md)). O incremento 0.6 entregou a base do reconhecimento facial com OpenCV e o 0.12 passou a exigir um desafio de movimento antes de liberar a porta ([facial-recognition.md](facial-recognition.md)); ainda falta calibrar com imagens autorizadas. O incremento 0.5 entregou identidades com consentimento, retenção e horários, mais o teste de reconhecimento simulado ([identities.md](identities.md)). O nobreak será usado somente para alimentar o computador; sua integração por software foi retirada do escopo. O quadro detalhado fica em [planning.md](planning.md) e no [Notion](https://app.notion.com/p/EverLock-3e8e2dde06ab809c893fcbd6a4958ff8).

| Etapa | Entrega | Critério de conclusão |
|---|---|---|
| 1. Base | Aplicação local, instalação, interface e banco | Iniciar pelo roteiro sem editar código |
| 2. Porta virtual | Estados, liberação temporária, entrada e ações manuais | Regras verificadas; nenhuma abertura automática na reinicialização |
| 3. Energia | Bateria matemática, consumo, recarga, relógio virtual e falhas | Cálculos reproduzíveis; desligamento crítico e recuperação coerentes |
| 4. Pessoas e permissões | Login, perfis, cadastro, revogação e histórico administrativo | Backend rejeita ações sem permissão; dados persistem |
| 5. Comunicação | Comandos identificados, validade, duplicatas, desconexão e política local | Comando antigo não executa após reconexão; observações antigas ficam identificadas |
| 6. Reconhecimento | Cadastro e comparação real de imagens; modo de testes separado | Imagens de teste distintas do cadastro; autorização consultada antes da liberação |
| Paralela: nobreak | Alimentar o computador e registrar um teste real | Continuidade medida; nenhuma leitura ou comando físico pela aplicação |
| 7. Interface e laboratório | Telas consolidadas, falhas e cenários reproduzíveis | Cenários compreensíveis sem conhecer o código |
| 8. Testes completos | Integração, falhas, recuperação e avaliação facial | Cenários obrigatórios aprovados e limitações registradas |
| 9. n8n, opcional | Alertas e relatórios por eventos | Integração não controla a porta e sua ausência não interrompe o sistema |
| 10. Entrega | Manual, relatório, diagramas e apresentação | Outra pessoa executa a demonstração pelo roteiro |

## Próximo incremento

O incremento 0.13 prepara a [avaliação facial](avaliacao-facial.md) e os [cenários integrados](cenarios-integrados.md). Execute o pipeline já implementado (YuNet, SFace, vetores cifrados e desafio de movimento) com imagens autorizadas distintas para cadastro e avaliação. Ajuste limites somente a partir dessas medições; consentimento da identidade pela própria pessoa segue pendente. Resultados preparados para testes continuam identificados como simulados. O protocolo de comandos e a reconexão sem execução de pedidos antigos estão descritos em [communication.md](communication.md).

A energia virtual usa Wh e parâmetros didáticos explícitos. Seus resultados não representam medições do nobreak. O grupo comprará somente esse equipamento adicional para sustentar o computador; autonomia e compatibilidade serão verificadas com o modelo real. Desligar o computador continua encerrando a aplicação.

## Dependências humanas

- O reconhecimento real exige imagens autorizadas para cadastro e avaliação.
- Webcam é opcional e depende de equipamento disponível e permissão de uso.
- Registrar o modelo do nobreak e as cargas alimentadas antes da demonstração real; não haverá driver no EverLock. Ver [ups.md](ups.md).
- Novas exigências acadêmicas podem alterar prioridade ou linguagem.

A ausência de imagens não impede desenvolver os demais módulos com resultados preparados, desde que identificados como simulados. Testes preparados não medem a precisão do reconhecimento facial.

Não há data final ou tamanho de equipe assumidos. O progresso será acompanhado pelas entregas verificadas, sem afirmar que uma função planejada já está pronta.
