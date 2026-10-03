# Cenários integrados do EverLock

Este roteiro cobre a parte automatizada da etapa 13 do planejamento. Une cadastro consentido,
desafio de giro, autorização, porta, energia, comunicação e persistência pela API pública.
O ensaio usa `FakeFaceEngine`, identificado como modelo `falso`, e capturas sintéticas diferentes
das usadas no cadastro. Não usa câmera, imagens de pessoas ou modelos OpenCV.

Os resultados comprovam regras de integração do simulador. A avaliação facial com imagens
autorizadas da etapa 12 e a reprodução por outra pessoa na interface continuam pendentes;
estes cenários não medem precisão biométrica, resistência a ataques ou autonomia de nobreak.

## Execução reproduzível

Na pasta do projeto, com as dependências de desenvolvimento instaladas:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_integrated_scenarios.py -q
```

Resultado esperado: três cenários aprovados. Cada execução cria um banco e uma chave biométrica
em uma pasta temporária do teste, com administrador de teste e motor falso. Não altera o banco
normal, não baixa modelos e não exige modificar o código da aplicação.

O relógio da porta e da energia fica pausado, com avanço explícito. O calendário da sessão é
fixo e o relógio monotônico dos comandos é controlado separadamente. Assim, os resultados não
dependem de esperar três segundos na máquina nem de acelerar o prazo de um comando remoto.

## 1. Reconhecimento, falha de energia e recuperação

1. Criar uma identidade com o termo de consentimento vigente e cadastrar três capturas falsas.
2. Obter um desafio, enviar uma captura frontal e três capturas com giro na direção pedida.
3. Conferir a trava liberada por três segundos virtuais e a porta ainda fechada.
4. Avançar dois segundos: resta um segundo. Avançar mais um: a trava engata.
5. Configurar carga virtual de 5% e cortar a alimentação. O dispositivo virtual desliga.
6. Tentar reconhecimento novamente: a indisponibilidade impede a liberação.
7. Usar saída interna, fechamento, chave e fechamento; as ações manuais continuam possíveis.
8. Restaurar a alimentação e avançar dois segundos de recuperação.

Aceite: o dispositivo retorna disponível, com porta fechada e trava engatada. O histórico tem
uma única liberação facial; nenhuma recuperação abre a porta ou repete o reconhecimento.

## 2. Revogação e exclusão depois de emitir um desafio

1. Cadastrar duas identidades consentidas e suas capturas falsas.
2. Reconhecer a primeira e deixar a liberação terminar após três segundos virtuais.
3. Emitir outro desafio para ela, revogar o consentimento e então enviar as capturas do desafio.
4. Repetir a sequência com a segunda identidade, usando exclusão completa.

Aceite: o desafio anterior à remoção não conserva autorização. A primeira tentativa é recusada
por falta de correspondência; depois da exclusão da última face, a segunda indica que não há
faces cadastradas. Nenhuma recusa muda a versão da porta nem cria uma nova liberação.
Permanece somente a identidade revogada, com zero amostras. A auditoria registra revogação
e exclusão.

O ensaio deixa a liberação anterior terminar antes da remoção. Não acrescenta uma regra de
cancelamento retroativo de uma liberação que já foi autorizada.

## 3. Reinício com liberação facial e comando remoto pendentes

1. Cadastrar uma identidade consentida e sua face falsa.
2. Configurar atraso remoto de 30 segundos e registrar um comando de liberação ainda pendente.
3. Liberar a trava por reconhecimento facial e emitir um novo desafio sem enviá-lo.
4. Encerrar e iniciar a aplicação sobre o mesmo banco; entrar novamente.
5. Consultar e repetir o comando com o mesmo identificador; avançar seu relógio além do prazo.
6. Enviar as capturas do desafio anterior ao reinício.
7. Criar um desafio novo e reconhecer a identidade preservada no banco.

Aceite: o cenário retoma pausado em 1×, com trava engatada e sem liberação antiga.
O comando termina com `restart_interrupted`; a repetição devolve o resultado existente e
nunca cria atuação remota. O desafio antigo é recusado com `challenge_expired`.
Cadastro e consentimento sobrevivem, e somente o novo desafio pode liberar a trava.

## Evidências e limites

Os três cenários estão em [test_integrated_scenarios.py](../tests/test_integrated_scenarios.py).
Eles complementam os testes isolados de reconhecimento, identidades, energia e comunicação.
Os eventos consultados com filtros distinguem as liberações faciais das remotas.

Para o ensaio na interface, use o cadastro e o reconhecimento explicitamente simulados descritos
em [identities.md](identities.md), junto com os roteiros de [energia](energy.md) e
[comunicação](communication.md). O motor falso deste teste não é disponibilizado na aplicação
normal. Para reproduzir o desafio pela câmera, siga [facial-recognition.md](facial-recognition.md)
e registre separadamente as imagens autorizadas, os resultados e as limitações da etapa 12.
