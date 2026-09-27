# Energia e tempo virtuais

Todos os números são parâmetros didáticos. Não representam autonomia física, eletrônica de proteção, conectividade real ou bateria capaz de manter o computador ligado.

## Modelo

| Parâmetro padrão | Valor | Significado |
|---|---|---|
| Capacidade | 40 Wh | Energia armazenável usada pelo modelo; não recebe outro desconto de capacidade útil |
| Carga inicial | 100% | Configurável de 0 a 100% |
| Consumo normal | 8 W | Carga básica sem a atuação da trava |
| Consumo econômico | 4 W | Usado na bateria a partir de 20% |
| Extra de atuação | 12 W | Somado ao perfil apenas durante a liberação de até 3 s virtuais |
| Consumo desligado | 0,1 W | Consumo residual após o desligamento crítico; pode ser zero |
| Potência de recarga | 10 W | Potência adicional fornecida pela rede para o carregador |
| Eficiência | 90% | Aplicada uma vez por sentido de conversão |
| Nível baixo / crítico | 20% / 5% | Economia e desligamento, respectivamente |

Na bateria: `energia retirada (Wh) = (consumo do perfil + extra ativo) × segundos / (3600 × eficiência)`.
Na rede: `energia carregada (Wh) = potência de recarga × eficiência × segundos / 3600`, limitada à capacidade.

A alimentação externa cobre o consumo e a recarga separadamente. O extra de atuação não está embutido no consumo básico. O limite de 5% é a única reserva de operação; não há uma segunda margem multiplicada escondida. A reserva continua alimentando apenas o consumo residual até 0 Wh. O modelo não simula tensão, corrente de pico ou falhas de componentes reais.

Sem liberações, o exemplo padrão permanece em operação por `(32 Wh × 0,9 / 8 W) + (6 Wh × 0,9 / 4 W) = 4,95 h`, ou 4h57min. Essa é uma consequência matemática dos parâmetros, não uma promessa de autonomia física. A estimativa considera a liberação atual, se houver, mas não prevê liberações futuras.

## Transições

Uma queda leva à bateria. Em 20%, o perfil muda para econômico; em 5%, o dispositivo virtual desliga e qualquer liberação termina. A posição da porta não muda. Se estava aberta, permanece aguardando fechamento. Saída, chave e fechamento representam ações mecânicas e continuam disponíveis.

O retorno da alimentação inicia uma recuperação de 2 segundos virtuais se o dispositivo estava desligado. Durante esse intervalo não são aceitos comandos eletrônicos de acesso. Ao concluir, o dispositivo volta a operar sem repetir uma liberação. Com relógio pausado é preciso avançar ou retomar o tempo. Nova queda durante a recuperação respeita a energia disponível.

O laboratório e sua API continuam acessíveis enquanto o dispositivo virtual está desligado. Isso permite observar e controlar a experiência; não representa telemetria real de um aparelho sem alimentação. Falhas independentes de internet/rede ainda pertencem à etapa de comunicação.

## Relógio e histórico

Porta, consumo, recarga, recuperação e avanços usam uma única linha de tempo. Pausar congela todos eles. Velocidades disponíveis: 1×, 60× e 600×. O avanço explícito exige pausa e aceita até 24 horas por requisição. Datas de auditoria continuam usando UTC real; cada evento novo também registra `simulated_at`.

O motor divide o intervalo nas fronteiras de liberação, carga, economia, desligamento e recuperação. Avançar horas não pula alertas. Em coincidência entre desligamento e fim da liberação, o desligamento prevalece.

Porta, energia, relógio e eventos são gravados juntos em SQLite. Há gravação em cada ação/transição e pontos de controle periódicos a cada 5 segundos reais ou virtuais, verificados pelo ciclo de 0,1 segundo real. Um encerramento abrupto pode perder o avanço desde o último ponto; em alta velocidade o intervalo virtual entre ciclos é maior. Um encerramento normal grava um ponto final. O tempo com o processo fechado não é simulado. Após reiniciar, o cenário retoma pausado em 1× e sem liberação ativa.

## Roteiro de demonstração

1. Em Energia, abra os parâmetros e aplique os valores padrão, com carga de 100%.
2. Corte a alimentação: a bateria assume, com o relógio pausado.
3. Libere a trava e avance 3 segundos: a liberação termina e o extra de consumo desaparece.
4. Avance 1 hora: observe a redução da energia em Wh.
5. Avance 6 horas: encontre os eventos de nível baixo e desligamento no histórico.
6. Use saída interna, fechamento e chave; o acesso eletrônico continua bloqueado.
7. Restaure a alimentação: observe Recuperando. Avance 3 segundos e confira que a trava não foi liberada.
8. Avance 1 hora: a carga aumenta em até 9 Wh, limitada à capacidade.

Para esgotar a reserva, mantenha a alimentação cortada e avance mais horas. Use os parâmetros para repetir o cenário sem apagar o histórico. As regras e a API são verificadas nos testes automatizados; a interface é conferida em celular e computador.
