# Decisões do EverLock

Registro inicial: 23 de setembro de 2026.

## 1. Simulação com uma aquisição física prevista

**Atualização confirmada pelo usuário em 26/09/2026:** o grupo comprará somente um nobreak pronto para alimentar o computador. Porta, trava e sensores continuam simulados; não haverá construção de fechadura ou montagem elétrica. O projeto usa um computador disponível, sem hospedagem paga obrigatória.

Essa decisão substitui a restrição anterior de nenhuma compra física. Modelo, custo e autonomia continuam indefinidos. A energia virtual permanece um modelo didático independente da futura telemetria real. O software funciona sem o nobreak. Alimentar o computador e ler informações do equipamento são integrações diferentes, detalhadas em [ups.md](ups.md).

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

## 12. Preparar o contrato antes de escolher o driver

O módulo do nobreak aceita observações validadas, identifica a fonte real e marca atraso após 15 segundos reais. Campos desconhecidos ficam nulos. Nesta versão não há produtor dessas leituras: a API informa `not_configured`. Escolher NUT ou software do fabricante somente após verificar o modelo e o sistema operacional. A primeira integração será de leitura; não oferecer desligamento físico pelo painel do simulador.
