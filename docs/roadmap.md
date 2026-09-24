# Etapas de desenvolvimento

O trabalho será executado em incrementos pela IA, com implementação, testes, correções e documentação em cada etapa. A equipe avalia os resultados, informa exigências acadêmicas e, quando necessário, fornece imagens autorizadas.

## Situação da primeira entrega

A base executável, a interface inicial, a persistência e os controles essenciais da porta virtual fazem parte desta entrega. Isso inicia a etapa 1 e antecipa parte da etapa 2. Os demais módulos continuam planejados.

| Etapa | Entrega | Critério de conclusão |
|---|---|---|
| 1. Base | Aplicação local, instalação, interface e banco | Iniciar pelo roteiro sem editar código |
| 2. Porta virtual | Estados, liberação temporária, entrada e ações manuais | Regras verificadas; nenhuma abertura automática na reinicialização |
| 3. Energia | Bateria matemática, consumo, recarga, relógio virtual e falhas | Cálculos reproduzíveis; desligamento crítico e recuperação coerentes |
| 4. Pessoas e permissões | Login, perfis, cadastro, revogação e histórico administrativo | Backend rejeita ações sem permissão; dados persistem |
| 5. Comunicação | Comandos identificados, validade, duplicatas, desconexão e política local | Comando antigo não executa após reconexão; observações antigas ficam identificadas |
| 6. Reconhecimento | Cadastro e comparação real de imagens; modo de testes separado | Imagens de teste distintas do cadastro; autorização consultada antes da liberação |
| 7. Interface e laboratório | Telas consolidadas, falhas e cenários reproduzíveis | Cenários compreensíveis sem conhecer o código |
| 8. Testes completos | Integração, falhas, recuperação e avaliação facial | Cenários obrigatórios aprovados e limitações registradas |
| 9. n8n, opcional | Alertas e relatórios por eventos | Integração não controla a porta e sua ausência não interrompe o sistema |
| 10. Entrega | Manual, relatório, diagramas e apresentação | Outra pessoa executa a demonstração pelo roteiro |

## Próximo incremento

Consolidar os testes da porta e acrescentar o motor de energia. Antes de implementar aceleração do tempo, definir um único relógio de simulação para liberação, bateria e comandos demonstrativos. As sessões de login, quando existirem, deverão usar tempo real.

A energia será expressa em Wh, com parâmetros didáticos explícitos. Seus resultados não serão apresentados como medições de bateria real. Desligar o computador continua encerrando a aplicação.

## Dependências humanas

- O reconhecimento real exige imagens autorizadas para cadastro e avaliação.
- Webcam é opcional e depende de equipamento disponível e permissão de uso.
- Novas exigências acadêmicas podem alterar prioridade ou linguagem.

A ausência de imagens não impede desenvolver os demais módulos com resultados preparados, desde que identificados como simulados. Testes preparados não medem a precisão do reconhecimento facial.

Não há data final ou tamanho de equipe assumidos. O progresso será acompanhado pelas entregas verificadas, sem afirmar que uma função planejada já está pronta.
