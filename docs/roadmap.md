# Etapas de desenvolvimento

O trabalho será executado em incrementos pela IA, com implementação, testes, correções e documentação em cada etapa. A equipe avalia os resultados, informa exigências acadêmicas e, quando necessário, fornece imagens autorizadas.

## Situação atual

A base e a porta virtual estão entregues. Energia, tema, contas e permissões estão implementados no incremento 0.3, com validação registrada em [status.md](status.md). A preparação para o nobreak real inclui contrato de leitura e separação da simulação, mas ainda não inclui driver. O quadro detalhado fica em [planning.md](planning.md) e no [Notion](https://app.notion.com/p/3e7e2dde06ab81f68b2ece96ce4a61a2).

| Etapa | Entrega | Critério de conclusão |
|---|---|---|
| 1. Base | Aplicação local, instalação, interface e banco | Iniciar pelo roteiro sem editar código |
| 2. Porta virtual | Estados, liberação temporária, entrada e ações manuais | Regras verificadas; nenhuma abertura automática na reinicialização |
| 3. Energia | Bateria matemática, consumo, recarga, relógio virtual e falhas | Cálculos reproduzíveis; desligamento crítico e recuperação coerentes |
| 4. Pessoas e permissões | Login, perfis, cadastro, revogação e histórico administrativo | Backend rejeita ações sem permissão; dados persistem |
| 5. Comunicação | Comandos identificados, validade, duplicatas, desconexão e política local | Comando antigo não executa após reconexão; observações antigas ficam identificadas |
| 6. Reconhecimento | Cadastro e comparação real de imagens; modo de testes separado | Imagens de teste distintas do cadastro; autorização consultada antes da liberação |
| Paralela: nobreak | Validar modelo/OS, alimentar computador e integrar leituras compatíveis | Continuidade medida; perda USB identificada; simulação não comanda equipamento |
| 7. Interface e laboratório | Telas consolidadas, falhas e cenários reproduzíveis | Cenários compreensíveis sem conhecer o código |
| 8. Testes completos | Integração, falhas, recuperação e avaliação facial | Cenários obrigatórios aprovados e limitações registradas |
| 9. n8n, opcional | Alertas e relatórios por eventos | Integração não controla a porta e sua ausência não interrompe o sistema |
| 10. Entrega | Manual, relatório, diagramas e apresentação | Outra pessoa executa a demonstração pelo roteiro |

## Próximo incremento

Acrescentar o protocolo de comandos: identificador único, validade, tratamento de duplicatas e confirmações de execução. Em seguida, simular perdas de internet, rede local e energia do dispositivo separadamente. Um comando antigo não poderá liberar a porta ao reconectar.

A energia virtual usa Wh e parâmetros didáticos explícitos. Seus resultados não representam medições do nobreak. O grupo comprará somente esse equipamento adicional para sustentar o computador; autonomia e compatibilidade serão verificadas com o modelo real. Desligar o computador continua encerrando a aplicação.

## Dependências humanas

- O reconhecimento real exige imagens autorizadas para cadastro e avaliação.
- Webcam é opcional e depende de equipamento disponível e permissão de uso.
- Informar marca/modelo do nobreak, interface de dados, sistema operacional e cargas alimentadas antes de implementar o driver; ver [ups.md](ups.md).
- Novas exigências acadêmicas podem alterar prioridade ou linguagem.

A ausência de imagens não impede desenvolver os demais módulos com resultados preparados, desde que identificados como simulados. Testes preparados não medem a precisão do reconhecimento facial.

Não há data final ou tamanho de equipe assumidos. O progresso será acompanhado pelas entregas verificadas, sem afirmar que uma função planejada já está pronta.
