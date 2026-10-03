# Estado do projeto

Versão atual: **0.13.0**. A retomada reúne os incrementos 0.5 a 0.12 enviados no arquivo do projeto, corrige o fluxo facial e prepara avaliação e cenários integrados. A base de contas e energia foi entregue no [PR #14](https://github.com/gustavonm20/EverLock/pull/14); marca e ajustes visuais, no [PR #16](https://github.com/gustavonm20/EverLock/pull/16). As verificações abaixo preservam o histórico de cada entrega e distinguem implementação de validação com pessoas reais.

## Entregue e verificado

- Aplicação local em Python, FastAPI e SQLite.
- Interface responsiva em português para celular e computador.
- Porta e trava virtuais com liberação temporária de três segundos.
- Entrada externa, fechamento, saída interna e chave manual simulada.
- Histórico persistente e recuperação segura após reinicialização.
- Indicação de conexão perdida e bloqueio dos controles no navegador.
- Contrato de API local, iniciador do Windows e configuração do VS Code.
- Testes automatizados das regras, API, concorrência, persistência e fronteira do prazo.

## Implementado no incremento 0.3

- Energia em Wh: consumo normal/econômico/residual, pulso de liberação, perdas e recarga.
- Relógio único com pausa, aceleração e avanço manual.
- Bateria baixa/crítica, esgotamento e recuperação de dois segundos virtuais.
- Ações manuais disponíveis sem energia virtual; retorno sem abertura automática.
- Persistência do cenário, migração aditiva e reinício pausado.
- Temas claro/escuro com sol/lua e preferência salva no navegador.
- Planejamento por entregas, dependências e critérios em [planning.md](planning.md).
- Login obrigatório por e-mail ou usuário, administrador inicial, papéis e cadastro automático com e-mail confirmado por link (sem aprovação administrativa).
- Senha com mínimo de 6 caracteres, maiúscula, minúscula, número e símbolo; sem máximo.
- Sessões de oito horas reais, logout, troca de senha, revogação e recuperação local.
- Histórico com autoria, limite de tentativas e proteção do último administrador ativo.
- Contrato de observações do nobreak separado da bateria virtual; nenhum driver real instalado.
- [Planejamento no Notion](https://app.notion.com/p/EverLock-3e8e2dde06ab809c893fcbd6a4958ff8) centralizado com as 18 tarefas anteriores, Kanban, checklists e páginas de apoio.

**101 testes aprovados** na suíte local completa, incluindo cadastro pendente/aprovação, política de senha, senha longa sem truncamento, compatibilidade de contas anteriores, recuperação por terminal e separação entre nobreak e simulação. Ruff e a verificação de diferenças também passaram. Há um aviso de descontinuação do cliente HTTP de testes, já acompanhado na [issue #13](https://github.com/gustavonm20/EverLock/issues/13); não houve falha de teste.

A interface de contas e os temas foram conferidos em computador e celular (390 × 844), incluindo persistência do tema e ausência de rolagem horizontal. O cadastro, a confirmação de senha e as restrições visíveis do usuário comum também foram conferidos. O [CI do incremento completo passou no GitHub](https://github.com/gustavonm20/EverLock/actions/runs/36295870556).

A `main` está protegida por regra ativa: pull request obrigatório, testes de qualidade aprovados, base atualizada, discussões resolvidas e bloqueio de exclusão/force push. Não há exceções de bypass.

## Incremento 0.4

- Comandos identificados com prazo real, recebimento, resultado e histórico persistente.
- Duplicatas sem nova atuação; conflito com versão antiga da porta é rejeitado.
- Revalidação de sessão/conta antes de executar; limite de envios e acesso por proprietário.
- Internet, rede local e energia independentes; observação remota antiga fica identificada.
- Interrupção/reinício cancelam comandos pendentes; reconexão não reabre a porta.
- Gravação atômica do resultado, estado da porta e evento de atuação.
- Painel remoto em português e controles administrativos de atraso e falhas.

A suíte completa passou com **116 testes**, incluindo 15 cenários novos de comunicação. Ruff passou. O aviso já acompanhado na issue #13 continua restrito ao cliente HTTP de testes. O [roteiro da nova etapa](communication.md) separa claramente os segundos reais do comando dos segundos virtuais de liberação.

## Incremento 0.5 (29/09/2026)

- Identidades biométricas separadas das contas, com apelido/código, ativação e janela de horário por dia da semana (inclusive atravessando a meia-noite).
- Consentimento versionado e registrado; revogação que apaga o cadastro; exclusão completa; retenção de 1 a 365 dias com exclusão automática.
- Cadastro **simulado** e teste de reconhecimento **simulado** (`match`/`no_match`), sem câmera, imagem, vetor, modelo ou nota de confiança inventada.
- Autorização consultada antes de o controlador liberar a trava; porta aberta ou dispositivo desligado continuam impedindo a liberação. Liberar não abre a porta.
- Auditoria e eventos citam só o número da identidade, para que a exclusão não deixe o apelido para trás.
- Seção **Identidades** (somente administrador) nos temas claro e escuro, sem rolagem horizontal no celular. Correção do atributo `pattern` dos campos de usuário, que o navegador rejeitava no console.

A suíte completa passou com **149 testes** (33 novos) e o Ruff passou. A interface foi conferida em um navegador real (cadastro, teste autorizado, recusas, tema escuro, celular e exclusão). Detalhes em [identities.md](identities.md). O CI do GitHub ainda não rodou nesta versão: ela precisa ser enviada por pull request.

## Contas por e-mail (29/09/2026)

- Login por e-mail ou usuário; cadastro com e-mail válido e único; a conta é criada na hora e só entra após abrir o link enviado por e-mail (24 horas, uso único, reenvio com senha). Removida a mensagem de "aguarde a aprovação".
- Credenciais SMTP somente por `everlock.env`/variáveis de ambiente, fora do Git; sem configuração o link aparece no terminal.
- Tela inicial sempre é o login. Textos secundários de **Sua conta** menores.
- A suíte completa passou com **159 testes** (10 novos, sem enviar e-mails reais). Limitação: o envio real por Gmail exige senha de app e não foi testado a partir daqui.

## Tipos de conta (30/09/2026)

- O cadastro passou a permitir escolher *Usuário* ou *Administrador*. Administrador exige código de convite de uso único (24 horas, hash no banco, máximo de 10 abertos), gerado e revogado por administradores em **Conta**.
- Descrições dos tipos aparecem no cadastro; recusas e convites ficam no histórico, sem o código. Detalhes em [accounts.md](accounts.md#convites-de-administrador).
- Verificado: 38 testes de convites, contas e e-mail e um teste no navegador (gerar convite, código errado recusado, cadastro como administrador, confirmação e entrada). A suíte completa não foi repetida nesta etapa.

## Reconhecimento facial, base (incremento 0.6, 01/10/2026)

- OpenCV (YuNet + SFace): cadastro com 5 fotos pela câmera do navegador, comparação 1:N com limite 0,45 e margem de ambiguidade, bloqueio após falhas, autorização por `evaluate()` antes de liberar a trava. Detalhes em [facial-recognition.md](facial-recognition.md).
- Vetores cifrados (AES-256-GCM) em `face_templates`, chave em `data/biometria.chave`; nenhuma imagem é gravada. Revogar, remover, excluir e vencer a retenção apagam os vetores. Termo de consentimento `2026-10-01`.
- Scripts `baixar_modelos.py` (com SHA-256) e `testar_rosto.py` (calibração). Novas dependências: `opencv-python-headless`, `cryptography`.
- Verificado: suíte completa com **181 testes** (22 novos) e Ruff; fluxo de câmera no navegador (cadastro de 5 fotos e reconhecimento) com câmera falsa do Chrome.
- **Não verificado:** o motor OpenCV real não rodou neste desenvolvimento (modelos inacessíveis); lógica testada com motor falso e interface com câmera falsa. **Sem prova de vida.** Limites não calibrados.

## Entrar com o rosto (incremento 0.7, 02/10/2026)

- Cadastro do rosto da própria conta (senha + termo + 5 fotos), vetores cifrados com escopo `conta`, remoção pelo dono ou por administrador, um rosto por conta.
- Entrada pelo rosto na tela de login, com desafio de giro sorteado, limite 0,55, margem de ambiguidade, bloqueio por falhas e mensagem **Face não cadastrada** (também no painel da porta).
- Verificado: suíte completa com **194 testes** (13 novos) e Ruff, e fluxo no navegador com câmera falsa: cadastro pela página Conta, entrada pelo rosto e mensagem para rosto desconhecido.
- **Não verificado:** motor OpenCV real, limites de giro (0,15 / 0,22) e sentido do giro com câmera real. Desafio de giro não é prova de vida robusta.

## Notificações por n8n (incremento 0.8, 02/10/2026)

- Webhook de saída opcional (`EVERLOCK_WEBHOOK_URL`) com gravidade (`info`/`warning`/`critical`), nível mínimo, assinatura HMAC-SHA256, fila em segundo plano, tentativas com espera, fila de 100 e sem redirecionamentos. Painel em **Atividade** e botão de teste. Detalhes em [notifications.md](notifications.md).
- Verificado: suíte completa com **209 testes** (15 novos) e Ruff; teste no navegador com um receptor HTTP local (envio assinado e contadores do painel); testes com servidor HTTP local (assinatura, tentativas, redirecionamento recusado, endereço não vaza em erros).
- **Não verificado:** recebimento por uma instância real do n8n; o trecho de conferência de assinatura em nó Code do n8n é exemplo, não testado.

## Recuperação de senha (incremento 0.9, 02/10/2026)

- **Esqueci minha senha** por e-mail: link de 1 hora e uso único, resposta idêntica para contas que existem ou não, envio depois da resposta, limite por computador, sessões encerradas ao redefinir. Detalhes em [accounts.md](accounts.md#esqueci-minha-senha).
- Verificado: suíte completa com **219 testes** (10 novos) e Ruff, e fluxo completo no navegador (pedido, link, senha fraca recusada, nova senha, senha antiga recusada, entrada com a nova).
- **Não verificado:** envio real por Gmail (precisa da senha de app).

## Decisões delegadas, modelos automáticos e backup (incremento 0.10, 02/10/2026)

- Botão remoto **Liberar trava** mantido como comando autenticado (decisão 20). Sessão aberta pelo rosto não cria convites nem administradores (decisão 21).
- `iniciar.cmd` baixa os modelos faciais sozinho na primeira vez. Novo `backup.cmd` e `python -m everlock backup | restaurar` (cópia consistente do banco + chave, senha opcional). Detalhes em [backup.md](backup.md).
- Verificado: suíte completa com **228 testes** (9 novos: cópia e restauração com e sem senha, arquivo adulterado e malicioso, sessão por rosto) e Ruff; comandos de backup e restauração executados na linha de comando.
- **Não verificado:** a baixa automática dos modelos pelo `iniciar.cmd` no Windows (aqui a rede bloqueia o endereço dos modelos; só o caminho de falha foi exercitado).

## Histórico com filtros e CSV (incremento 0.11, 02/10/2026)

- Em **Atividade**: filtros por resultado, origem, texto e período, e **Baixar CSV** (UTF-8 com BOM e `;` para o Excel em português; proteção contra fórmulas). Mesmos filtros na API (`/api/events`, `/api/events/export.csv`).
- Novo [roteiro de apresentação](roteiro-apresentacao.md) com sequência, falas e respostas honestas para a banca.
- Verificado: suíte completa com **237 testes** (9 novos: filtros, curingas literais, datas, validação, permissões, CSV e fórmulas) e Ruff; filtros, limpar e CSV conferidos no navegador. O histórico de **contas** e de **identidades** continua fora do CSV.

## Desafio de movimento na porta (incremento 0.12, 03/10/2026)

- O reconhecimento facial real da porta agora exige um desafio de giro sorteado, de uso único e válido por 45 segundos, antes de comparar a identidade e liberar a trava.
- A captura começa de frente, pede giro curto para um lado e confirma que o rosto permaneceu o mesmo. Foto parada, lado errado, troca de rosto, desafio vencido ou reutilizado mantêm a trava engatada.
- O fluxo continua administrativo e local, não grava imagens e não altera o reconhecimento simulado. O desafio reduz o uso de foto parada, mas não é prova de vida forte: vídeo ou foto movimentada ainda podem enganar o sistema.
- Verificado: suíte completa com **238 testes** e Ruff; os cenários novos cobrem movimento correto, ausência de giro, lado errado, troca de rosto, expiração, uso único e permissões. A calibração do giro e da similaridade com câmera e imagens autorizadas continua pendente.

## Retomada, avaliação e cenários integrados (incremento 0.13, 03/10/2026)

- Corrigidos cancelamento de câmera, captura e respostas tardias; desafio ligado à sessão, substituição do desafio anterior, uso único e revalidação do prazo e da autorização antes de liberar a trava. Todas as amostras aproveitadas devem corresponder ao rosto inicial.
- Novo `DELETE /api/recognition/challenge/{challenge_id}` cancela a tentativa da própria sessão, inclusive durante a leitura das imagens. A análise não impede que outra requisição revogue a sessão ou cancele o desafio.
- O login facial da conta recebeu o mesmo tratamento de operação assíncrona, todas as amostras e expiração, com `DELETE /api/auth/face/challenge/{challenge_id}`. A galeria é consultada novamente antes de criar sessão; cadastro da conta revalida a sessão antes de salvar os vetores.
- Ferramenta local da etapa 12 em `scripts/avaliar_rostos.py`: manifesto com autorização, separação de cadastro/teste, identificação 1:N, falhas de captura separadas, erros e latência. Relatórios não incluem imagens, vetores ou caminhos e não alteram limites do aplicativo. Veja [o protocolo](avaliacao-facial.md).
- Três [cenários integrados da etapa 13](cenarios-integrados.md) pela API cobrem reconhecimento, liberação de três segundos, energia, saída/chave manuais, revogação/exclusão e reinício sem repetir atuação facial ou comando remoto. O motor dos testes é explicitamente falso.
- Documentação antiga alinhada a confirmação de e-mail, convites, cadastro facial, consentimento atual, cifra, backup e limites de validação. Novo [relatório técnico](relatorio-tecnico.md) consolida arquitetura, método e aceites para o grupo. Dependências fixadas alinhadas ao ambiente validado.
- OpenCV 4.13 carregou os modelos locais YuNet/SFace e recusou uma imagem vazia; nenhum rosto humano foi usado nesta retomada. Precisão, sentido do giro, apresentação de fotos/vídeos e calibração continuam sem medição real.

Validação final desta retomada: **271 testes aprovados** em uma execução completa sobre a cópia destinada à publicação, Ruff aprovado e sintaxe dos scripts da interface verificada. Os testes incluem a CLI sem sobrescrever relatórios, medições de latência com relógio controlado e regressões de cancelamento/expiração. Nove cenários de câmera/API simuladas conferiram cancelamento nas duas interfaces; não foi um ensaio visual com câmera real. Permanece somente o aviso do cliente HTTP de testes já acompanhado na [issue #13](https://github.com/gustavonm20/EverLock/issues/13).

## Pendências de aceite e validação

- Consentimento dado pela própria pessoa (hoje o administrador o registra).
- Transporte remoto entre computadores e implantação compartilhada com HTTPS.
- Avaliação com imagens autorizadas pelo novo protocolo e ensaio de ataques de apresentação; o desafio simples não é prova de vida forte.
- Relatórios periódicos por n8n (as notificações de eventos já existem).
- Empacotamento final e ensaio do roteiro de apresentação.
- Teste real de continuidade com o nobreak alimentando o computador; integração por software foi retirada do escopo.

## Escopo físico atualizado

O grupo comprará somente um nobreak pronto para sustentar o computador. Porta, trava e sensores continuam virtuais. Marca/modelo, valor e autonomia não foram informados. Conforme decisão de 28/09/2026, não haverá integração de leitura ou controle do nobreak. A seção Status Nobreak informa isso e mantém os cenários virtuais em uma área de testes recolhida.

## Ajustes de interface de 28/09/2026

- Login como primeira tela, mesmo sem contas; cadastro apenas por escolha explícita.
- Logo fornecida pelo grupo com fundo transparente e contraste para os dois temas.
- Entrada local identificada como reconhecimento facial, ainda sem coleta ou atuação biométrica; não há botão de liberação direta nessa área.
- Remoção do cartão duplicado Nobreak real e da consulta periódica de telemetria.
- Textos secundários de Sua conta reduzidos; títulos mantidos.
- A suíte continua com 116 testes aprovados após a atualização das permissões e do contrato informativo do nobreak.

Consulte [roadmap.md](roadmap.md) para as etapas e critérios de conclusão.
