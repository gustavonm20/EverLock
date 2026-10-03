# Relatório técnico — EverLock 0.13.0

Referência: 03/10/2026. Este relatório descreve o projeto implementado e distingue as
verificações automatizadas dos aceites ainda necessários para a apresentação.

## Escopo do protótipo

O EverLock é um laboratório local de controle de acesso. Porta, trava, sensores, bateria,
interrupções de rede e ações mecânicas são virtuais. A câmera do navegador e o processamento
facial com OpenCV podem usar imagens reais, quando disponíveis e autorizadas. Reconhecer um
rosto pode liberar a trava virtual; o projeto não aciona uma fechadura física.

O nobreak previsto alimentará o computador como equipamento externo. Não há leitura de
carga, controle por USB/rede, driver ou integração com o aplicativo. A autonomia exibida
nos cenários de energia vem de parâmetros didáticos e não mede esse equipamento.

## Arquitetura existente

A aplicação reúne uma interface em HTML, CSS e JavaScript, uma API em Python/FastAPI e um
banco SQLite. Deve executar com um único processo do servidor local. Contas e sessões
autenticam operadores; identidades representam as pessoas que podem receber acesso pela
câmera da porta. O rosto opcional usado para entrar na conta tem cadastro separado.

O controlador concentra as regras da porta, energia e recuperação. Um relógio virtual
permite pausa, aceleração e avanços reproduzíveis. Sessões e prazos de comandos remotos
usam tempo real independente. Porta, energia, eventos e decisão final de comando são
persistidos de forma transacional. Reiniciar encerra liberações antigas e comandos
incompletos, retomando o cenário pausado em 1×.

O canal remoto simulado trata identificador único, prazo, duplicatas, versão da porta e
revalidação da sessão. O histórico oferece filtros e exportação CSV. SMTP atende confirmação
de e-mail e recuperação de senha; o webhook opcional pode enviar alertas ao n8n em segundo
plano, sem participar da autorização ou impedir a operação da porta virtual.

## Do rosto à liberação

O fluxo de acesso é: **capturas → desafio e comparação facial → identidade candidata →
autorização atual → controlador → liberação temporária da trava**.

O motor local usa YuNet para detectar o rosto e seus pontos, e SFace para alinhar e produzir o vetor.
Antes da liberação facial, um desafio sorteia um giro, tem validade de 45 segundos, uso
único e vínculo à sessão que o solicitou. A captura inicial deve estar frontal, alguma
captura posterior deve mostrar o giro solicitado e todas as amostras aproveitadas devem
corresponder ao mesmo rosto. A interface solicita cancelamento ao encerrar a operação.

A comparação 1:N indica uma identidade, com recusa de desconhecidos e ambiguidades.
O servidor então confere consentimento, retenção, ativação e janela de horário. Revalida
a sessão, o desafio e seu prazo antes de atuar. O controlador exige dispositivo virtual
disponível e porta fechada. A trava fica liberada por três segundos virtuais; abrir a
porta exige uma ação separada. Saída interna, chave e fechamento são ações manuais simuladas.

## Dados e consentimento

No cadastro simulado, não há imagem nem vetor. No cadastro facial da aplicação, imagens
são processadas em memória e os vetores persistidos usam AES-256-GCM, com chave separada
do banco. A cifra protege o armazenamento, mas o acesso ao computador, banco e chave
continua sendo uma fronteira de confiança.

O termo vigente é versionado. Atualmente o administrador registra a concordância da
identidade; obter esse aceite diretamente da própria pessoa continua pendente. Revogação
apaga o cadastro facial e impede novas liberações. Exclusão remove identidade, consentimento
e horários; o fim da retenção também exclui a identidade nas verificações previstas.
Eventos da identidade citam seu número, preservando autoria e histórico sem o apelido.
As contas têm auditoria própria, que pode identificar o nome de usuário do operador.

## Método de avaliação facial

A ferramenta `scripts/avaliar_rostos.py` avalia identificação 1:N fora do aplicativo,
sem criar identidades ou liberar a trava. Um manifesto registra autorização e códigos
dos participantes. As imagens de teste devem ser distintas do cadastro; pessoas
autorizadas fora da galeria permitem observar falsas aceitações.

Cada imagem válida é comparada com toda a galeria, usando a melhor amostra de cada pessoa
e a margem de ambiguidade. O relatório separa desconhecidos aceitos, cadastrados recusados,
trocas de identidade e identificações corretas. Informa numeradores, denominadores,
latência e limites usados; uma taxa sem denominador fica ausente (`null`).

Falhas de captura, como arquivo ilegível, rosto ausente, múltiplos rostos ou desfoque,
são registradas separadamente e não entram no denominador das taxas de identificação.
Cadastros recusados também aparecem separados, sem transformar seus testes em desconhecidos.
Essas exclusões precisam ser examinadas junto das taxas para avaliar o uso do sistema.

A ferramenta foi verificada com dados sintéticos. Ela não valida o desafio de giro,
autorização ou resistência a fotos e vídeos. Não ajusta limites automaticamente.
Imagens e resultados individuais devem permanecer no conjunto local autorizado; o
relatório usa códigos, que ainda podem identificar participantes para quem conhece a relação.

## Cenários integrados automatizados

Os três cenários da etapa 13 usam a API pública, bancos temporários e `FakeFaceEngine`,
explicitamente identificado como motor falso:

- Cadastro consentido, desafio, liberação de três segundos sem abertura automática,
  desligamento virtual, ações manuais e recuperação sem repetir a liberação.
- Reconhecimento seguido de revogação ou exclusão, com recusa de uma tentativa cujo
  desafio havia sido emitido antes da remoção.
- Reinício sobre o mesmo banco, preservando cadastro e consentimento, mas encerrando
  liberação, desafio antigo e comando remoto pendente sem repetir atuação.

Essas evidências verificam a integração das regras. Não constituem uma medição de
precisão facial ou uma demonstração com pessoas reais.

## Verificação da retomada

Na cópia de publicação, a suíte completa passou com **271 testes**, além de Ruff e checagem
de sintaxe dos scripts da interface. O aviso existente do cliente HTTP não provocou falha.
Os testes da avaliação e da integração usam dados sintéticos; nove cenários de câmera/API
simuladas verificaram o cancelamento nas interfaces faciais. OpenCV carregou os modelos
locais e recusou uma imagem vazia, sem usar imagens humanas. Essas verificações não
substituem calibração, ensaio visual com câmera real ou revisão da equipe.

## Limites e aceites pendentes

O protótipo permanece local e não está validado para proteger uma porta física. Os
limites faciais são provisórios; o giro simples não é uma prova de vida robusta.
Para concluir as etapas de avaliação, integração e apresentação, faltam:

- Executar a avaliação com imagens autorizadas e separadas, revisar erros e registrar
  condições, resultados e eventual calibração; conferir câmera, direção do giro e ataques
  de apresentação com foto/vídeo.
- Implementar o aceite do consentimento da identidade pela própria pessoa.
- Fazer outro apresentador reproduzir o manual e registrar a evidência do ensaio.
- Validar o envio SMTP real, o recebimento por uma instância n8n e os relatórios periódicos
  previstos; os testes locais de envio não comprovam essas integrações externas.
- Verificar continuidade e retorno da alimentação com nobreak e computador reais,
  preservando a decisão de não integrar o equipamento ao software.

Fontes do projeto: [arquitetura](architecture.md), [identidades](identities.md),
[reconhecimento facial](facial-recognition.md), [avaliação](avaliacao-facial.md),
[cenários integrados](cenarios-integrados.md), [contas](accounts.md),
[notificações](notifications.md), [nobreak](ups.md) e [planejamento](planning.md).
