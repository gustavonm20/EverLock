# Decisões do EverLock

Registro inicial: 23 de setembro de 2026.

## 1. Simulação com uma aquisição física prevista

**Atualização confirmada pelo usuário em 26/09/2026:** o grupo comprará somente um nobreak pronto para alimentar o computador. Porta, trava e sensores continuam simulados; não haverá construção de fechadura ou montagem elétrica. O projeto usa um computador disponível, sem hospedagem paga obrigatória.

Essa decisão substitui a restrição anterior de nenhuma compra física. Modelo, custo e autonomia continuam indefinidos. Em 28/09/2026, o grupo definiu o uso somente na alimentação do computador, sem telemetria ou integração ao software. A energia virtual permanece um modelo didático independente. O software funciona sem o nobreak; veja [ups.md](ups.md).

## 2. Python no backend do MVP

**Decisão de implementação:** adotar Python para manter API, simulador, testes e futura visão computacional na mesma linguagem.

**Preferência registrada pelo usuário:** Python e Java são opções válidas. Python não é uma exigência permanente. Java permanece uma alternativa se surgir uma razão técnica ou acadêmica concreta; a base atual não precisa de uma combinação das duas linguagens.

FastAPI organiza a API, SQLite mantém os dados locais e HTML/CSS/JavaScript fornecem uma interface única para diferentes tamanhos de tela.

## 3. Primeiro incremento pequeno e executável

Entregar primeiro inicialização, interface, porta virtual e histórico. Login, biometria, energia e conectividade serão acrescentados em etapas próprias. O desenvolvimento pode antecipar pequenas partes de uma etapa quando isso torna a base demonstrável, sem declarar o projeto completo.

## 4. Estado controlado pelo servidor

O backend decide se a porta pode abrir. Liberação, posição da porta e resultado de ações são conceitos separados. O prazo de liberação é de três segundos virtuais. Desde a etapa de energia, um relógio comum controla porta, bateria e recuperação, alimentado pelo tempo monotônico do servidor.

Ao reiniciar, recuperar a posição da porta e encerrar a liberação anterior. Nunca repetir uma abertura porque havia uma ação em andamento antes do encerramento.

## 5. Execução local nesta fase

A base atende somente em `127.0.0.1`. A versão 0.3 acrescenta autenticação e papéis locais; isso não autoriza exposição à rede ou à internet. HTTPS e revisão de implantação antecedem operação compartilhada.

O histórico registra ações do simulador e da administração com autoria. Usar nomes de conta de demonstração; não há necessidade de fotografias nesta fase.

## 6. Reconhecimento real e resultados preparados serão distintos

Está planejado processar imagens reais com OpenCV, YuNet e SFace. Resultados preparados serão usados para desenvolvimento e testes da lógica, com identificação explícita na interface e nos eventos.

Uma comparação facial não será descrita como prova de presença de pessoa viva. A liberação continuará dependendo de autorização válida.

## 7. n8n opcional

A automação poderá gerar alertas e relatórios depois do sistema principal. Não autorizará pessoas, não liberará a porta e não receberá imagens nem modelos biométricos. O EverLock deverá continuar funcionando sem esse serviço.

## 8. Desenvolvimento e verificação pela IA

A IA implementa, executa testes, corrige falhas e documenta. A equipe avalia a demonstração e fornece informações que não podem ser inferidas, como exigências da instituição e imagens autorizadas. O registro de progresso deve distinguir funções implementadas, verificações realizadas e trabalho pendente.

## 9. Energia didática e recuperável

Usar Wh, contabilizar a eficiência uma vez e separar consumo normal, econômico, residual e adicional durante a liberação. O modelo troca para economia em 20% e desliga em 5%; restaurar alimentação inicia recuperação de dois segundos virtuais sem liberar a trava. Parâmetros são hipóteses de laboratório, sem promessa de autonomia física. O estado reinicia pausado, evitando interpretar horas sem processo como simulação executada.

## 10. Tema no navegador

Oferecer sol/lua sem dependências novas. Salvar a escolha localmente e seguir o tema do sistema quando ainda não houver preferência. A escolha visual não participa de autorização nem modifica dados da simulação.

## 11. Sessões independentes da simulação

Contas e sessões vivem em tabelas próprias. Senhas usam scrypt com salt; somente o hash do token de sessão é salvo. Sessões expiram em oito horas reais e são revogadas por logout, alteração de papel, ativação ou senha. Não remover o último administrador. A autorização e a atuação compartilham a trava do controlador para evitar uma corrida com revogação.

**Ajuste solicitado em 27/09/2026:** oferecer cadastro na tela de entrada e aceitar novas senhas com mínimo de 6 caracteres, sem máximo, exigindo maiúscula, minúscula, número e símbolo. Login de contas anteriores permanece compatível. O cadastro aguarda aprovação administrativa e não permite escolher privilégios; essa é a política inicial de implementação.

## 12. Nobreak externo, sem integração por software

A decisão de 28/09/2026 substitui a preparação anterior de telemetria. O aplicativo não carrega o monitor antigo nem consulta USB, rede ou software de fabricante. Status Nobreak informa ausência de monitoramento e a API de compatibilidade responde `not_monitored`, sem medições. A continuidade será demonstrada com o equipamento alimentando o computador. Os cenários matemáticos continuam identificados e recolhidos para testes.

## 13. Identidades sem dados biométricos nesta etapa

**Decisão de 29/09/2026, seguindo o roteiro (próximo incremento):** implementar antes do reconhecimento real a estrutura que ele precisará respeitar: identidades separadas das contas, consentimento versionado e registrado, revogação que apaga o cadastro, exclusão completa, retenção com exclusão automática e janela de horário. O "cadastro" é um marcador simulado; nenhuma imagem, vetor ou modelo é coletado ou armazenado.

- **Apelido, não nome:** a identidade usa um apelido ou código, e eventos e auditorias citam apenas o número (não reutilizado), para que a exclusão não deixe rastros.
- **Exclusão em vez de bloqueio na retenção:** ao vencer, a identidade é apagada. Revogar também apaga o cadastro e impede reativação; voltar exige novo consentimento.
- **Sem nota de confiança:** o teste simulado não inventa percentuais; retorna apenas o resultado preparado, sempre identificado como simulado.
- **Autorização antes da atuação:** a decisão consulta consentimento, cadastro, ativação e horário; só depois o controlador aplica as regras da porta (dispositivo ligado, porta fechada).
- **Limitação assumida:** hoje o administrador registra que a pessoa consentiu. O consentimento pela própria pessoa fica para a etapa com imagens reais.
- **Horário local:** a janela usa o horário de calendário do computador, não o relógio virtual.

## 14. Cadastro com e-mail confirmado (substitui a aprovação administrativa)

**Decisão de 30/09/2026, a pedido do responsável pelo projeto:** o cadastro cria a conta na hora, sem aprovação de administrador, mas exige e-mail válido e único e só libera o acesso após o link enviado ao e-mail.

- **Confirmar em vez de aprovar:** o e-mail prova que a pessoa controla o endereço; sem isso, qualquer um criaria contas com e-mails de terceiros.
- **Segredos fora do repositório:** a senha do SMTP fica em `everlock.env` (ignorado pelo Git). Uma senha compartilhada em conversa deve ser trocada e substituída por uma senha de app.
- **Falha no envio desfaz o cadastro,** para não deixar contas que ninguém consegue confirmar; o reenvio exige a senha da conta.
- **Sem SMTP, link no terminal:** mantém o laboratório usável sem depender de internet; o link nunca volta pela API.
- **Administradores respondem pelo e-mail** das contas que criam, que já nascem confirmadas.

## 15. Escolha do tipo de conta protegida por convite

**Decisão de 30/09/2026, a pedido do responsável pelo projeto:** o cadastro oferece Usuário ou Administrador; administrador exige um código de convite de uso único gerado por outro administrador. Trade-off: um passo a mais para criar administradores, em troca de nenhuma escalada de privilégio por formulário público. O primeiro administrador continua sendo criado na configuração inicial.

## 16. Reconhecimento facial com OpenCV e vetores cifrados

**Decisão de 01/10/2026, a pedido do responsável pelo projeto:** usar OpenCV (detector YuNet e reconhecedor SFace) para o reconhecimento facial.

- **OpenCV em vez de dlib/DeepFace:** instala com `pip` no Windows, sem compilador e sem TensorFlow. Trade-off: precisão menor que modelos grandes.
- **Câmera no navegador, análise no servidor:** reaproveita a interface e o preview; o servidor local nunca recebe nada de outra máquina. Trade-off: exige administrador logado na máquina da câmera.
- **Guardar vetores, nunca imagens, e cifrados:** reduz o dano de um vazamento; a chave fica fora do banco. Trade-off: perder a chave obriga a recadastrar.
- **Rosto não autoriza sozinho:** ele só indica a identidade; `evaluate()` decide (consentimento, retenção, horário). Liberar a trava continua sem abrir a porta.
- **Recusar o ambíguo e bloquear tentativas:** troca algumas falsas rejeições por menos falsas aceitações.
- **Termo de consentimento novo (2026-10-01):** o antigo prometia não coletar dado biométrico; identidades antigas precisam ser recriadas para usar o rosto.
- **Limitação assumida:** sem prova de vida; adequado a porta virtual, não a controle de acesso real.
- O teste de que "nenhuma coluna de imagem existe" substitui o antigo "nenhum BLOB": agora há vetores cifrados, mas ainda nenhuma imagem.

## 17. Entrada no aplicativo pelo rosto, com desafio de giro

**Decisão de 02/10/2026, a pedido do responsável pelo projeto:** cada conta pode cadastrar o rosto e entrar com ele.

- **Opcional e sempre com senha de reserva:** o rosto é uma segunda porta, nunca a única. Cadastrar exige a senha atual e o aceite de um termo próprio.
- **Desafio de giro sorteado:** barra foto parada, ao custo de pedir um movimento. Trade-off: não é prova de vida forte (vídeo gravado pode passar); documentado, e a porta física não depende disso.
- **Limite mais rígido (0,55) que o da porta (0,45):** autenticar no aplicativo é mais grave que liberar uma porta virtual.
- **Um rosto, uma conta; vetores com escopo `conta`:** evita ambiguidade e mistura com a porta.
- **Sem enumeração de contas:** a mensagem de rosto desconhecido não diz de quem seria.
- **Recomendação:** administradores devem preferir só a senha. Se o grupo quiser, um passo seguinte é impedir a entrada por rosto em contas de administrador.

## 18. Notificações por webhook assíncrono e opcional

**Decisão de 02/10/2026, seguindo o roteiro (n8n):** avisos de eventos saem por um webhook configurável, sem dependência nova (usa `urllib`).

- **Fila e thread própria:** a porta e o login jamais esperam a rede. Trade-off: mensagens na fila se perdem se o programa fechar, e a fila cheia descarta a mais antiga; o histórico do EverLock continua sendo o registro oficial.
- **Desligado por padrão e filtrado por gravidade:** evita inundar o n8n com eventos de rotina; `info` fica disponível para quem quiser tudo.
- **Assinatura HMAC com timestamp:** o receptor confere a origem e rejeita repetições. Trade-off: exige código no receptor; sem segredo, a URL passa a ser o único segredo.
- **Sem redirecionamentos e sem endereço em mensagens de erro:** o destino não pode ser trocado no meio e o painel não vaza a URL (que pode conter um token).
- **Só texto de eventos:** nenhuma imagem, vetor ou apelido sai do computador.

## 19. Recuperação de senha por link de e-mail

**Decisão de 02/10/2026, proposta do desenvolvimento:** quem esquece a senha a redefine por um link enviado ao e-mail confirmado, em vez de depender do console do administrador.

- **Resposta igual e envio depois dela:** não deixa descobrir quais e-mails têm conta, nem pelo texto nem pelo tempo. Trade-off: quem erra o e-mail não recebe aviso de erro.
- **Link de 1 hora, uso único, hash no banco, no fragmento `#`:** não aparece em registros do servidor e um vazamento do banco não entrega links válidos.
- **Encerra todas as sessões e limpa o bloqueio:** se alguém tinha a senha antiga, perde o acesso. Trade-off: a pessoa precisa entrar de novo em todos os lugares.
- **Só contas ativas, aprovadas e confirmadas:** mantém a regra de que e-mail não confirmado não vale nada.
- **Limitação assumida:** quem controla o e-mail controla a conta. O rosto cadastrado não é removido na redefinição.

## 20. O comando remoto "Liberar trava" não exige reconhecimento facial

**Decisão de 02/10/2026, delegada pelo responsável pelo projeto (critério: praticidade para o usuário):** o botão remoto continua como comando autenticado pelo login.

- **Por quê:** o reconhecimento por câmera só faz sentido para quem está diante dela. Exigi-lo num comando remoto obrigaria a ir até o computador, anulando o motivo do comando remoto.
- **O rosto tem o seu lugar:** a liberação de quem está no local é o painel de reconhecimento facial. A tela do comando remoto agora diz isso.
- **Trade-off:** o comando remoto vale tanto quanto o login. Quem rouba uma sessão pode liberar a trava virtual; a sessão dura no máximo 8 horas e cada comando fica no histórico (e vai ao n8n se configurado).

## 21. Administradores podem entrar pelo rosto, mas essa sessão não eleva privilégios

**Decisão de 02/10/2026, delegada pelo responsável pelo projeto (critério: praticidade para o usuário):** em vez de proibir o rosto para administradores, a sessão aberta pelo rosto fica proibida de criar convites, criar administradores e promover contas.

- **Por quê:** proibir tiraria a conveniência de quem mais usa o app. O risco real do rosto (foto ou vídeo enganar a câmera) é a escalada de privilégio; bloquear só isso custa quase nada no dia a dia.
- **Como:** a sessão guarda o método de entrada (`password` ou `face`); três ações exigem `password`. Sessões antigas contam como senha.
- **Trade-off:** uma sessão por rosto de administrador ainda vê contas e histórico e comanda o laboratório; quem quiser mais rigor pode simplesmente não cadastrar o rosto dessa conta.

## 22. Modelos baixados sozinhos e cópia de segurança por comando

**Decisão de 02/10/2026 (critério: reduzir o que o usuário precisa fazer):**

- **`iniciar.cmd` baixa os modelos faciais** na primeira vez (SHA-256 conferido). Falha de rede não impede o app. Trade-off: a primeira abertura demora mais e precisa de internet uma vez.
- **`backup.cmd` / `python -m everlock backup`** gera uma cópia consistente do banco (mesmo com o app aberto) junto com a chave dos rostos, com senha opcional (AES-256-GCM, chave por scrypt). `restaurar` recusa sobrescrever sem `--forcar` e guarda os dados atuais numa pasta de reserva. Trade-off: banco e chave no mesmo arquivo concentram o que é sensível; por isso a senha é recomendada, e sem ela o programa avisa.

## 23. Desafio de movimento também na liberação facial da porta

**Decisão de 03/10/2026, seguindo a próxima etapa documentada:** o reconhecimento real da porta exige começar de frente e cumprir um giro curto sorteado antes de comparar a identidade.

- **Uso único e 45 segundos:** reduz reutilização acidental e impede guardar um desafio para depois.
- **Mesmo rosto nas duas fases:** o vetor da foto virada precisa continuar compatível com a identidade encontrada na foto de frente.
- **Sem promessa de prova de vida:** foto parada é recusada, mas vídeo ou foto movimentada ainda podem passar. A função continua restrita à porta virtual e precisa ser calibrada com a câmera real.
- **Modo simulado preservado:** testes preparados continuam separados e não fingem ter verificado movimento ou presença real.
