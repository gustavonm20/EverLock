# Nobreak: alimentação externa do computador

## Escopo confirmado em 28/09/2026

O grupo comprará um nobreak pronto **para alimentar o computador**. O equipamento não será integrado ao EverLock por USB, rede, driver ou API. Porta, trava e sensores continuam virtuais. Modelo, preço e duração de backup não foram informados.

Essa decisão substitui a proposta anterior de desenvolver um adaptador para ler carga e autonomia. Não é necessário instalar NUT, biblioteca de USB ou software de integração para executar o EverLock.

```mermaid
flowchart LR
    Tomada["Alimentação elétrica"] --> Nobreak["Nobreak pronto"] --> Computador["Computador"]
    Computador --> Aplicacao["EverLock em execução"]
    Aplicacao --> Simulacao["Porta e cenários virtuais"]
```

## O que a aplicação mostra

A seção **Status Nobreak** explica o uso externo e informa **Sem monitoramento pelo aplicativo**. Não exibe porcentagem, presença de energia ou autonomia reais, pois não recebe essas informações. A conexão com o servidor prova apenas que a aplicação respondeu.

O cartão separado **Nobreak real** foi retirado. A rota autenticada `GET /api/ups`, mantida para compatibilidade, retorna `source: "external_equipment"`, `status: "not_monitored"`, `observation: null` e `controls_available: false`. Nenhuma rota controla o equipamento. O antigo módulo isolado `ups.py` não é carregado pela aplicação e não constitui uma integração ativa.

## Simulação de energia

Os controles matemáticos anteriores permanecem em **Status Nobreak > Cenários virtuais para testes**, recolhidos e disponíveis para administradores. Alteram somente `/api/simulation/*`: bateria virtual, tempo, disponibilidade do dispositivo virtual e suas regras de recuperação. Não são leituras do nobreak nem cortam energia do computador.

Assim, é possível testar falhas do software sem desligar o computador. Os valores em Wh e a autonomia estimada continuam didáticos; consulte [energy.md](energy.md).

## Funcionamento durante falta de energia

- Enquanto o nobreak sustentar o computador, o processo do EverLock pode continuar funcionando.
- Se o computador desligar, o servidor e a interface local deixam de funcionar; uma simulação não mantém o computador ligado.
- Ao reiniciar o EverLock, liberações anteriores não são retomadas e comandos pendentes são cancelados.
- Alimentar o computador não garante conectividade do roteador ou do provedor.

## Verificação com o equipamento

1. Registrar modelo do nobreak, computador e demais cargas alimentadas.
2. Conferir compatibilidade e conexão conforme o manual do equipamento.
3. Salvar arquivos e iniciar o EverLock com dados de demonstração.
4. Realizar uma interrupção supervisionada conforme o manual, registrando horário e continuidade da aplicação.
5. Restaurar a alimentação com reserva suficiente e conferir o histórico do aplicativo.

Não há prazo de autonomia prometido. O resultado deve ser medido com o equipamento e a carga reais. O aplicativo não precisa descobrir ou monitorar o nobreak para funcionar.
