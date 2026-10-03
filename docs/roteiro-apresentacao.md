# Roteiro de apresentação (cerca de 10 minutos)

Roteiro para demonstrar o EverLock numa banca ou feira. Prepare tudo **antes**: `.\iniciar.cmd` rodado uma vez (instala as bibliotecas e baixa os modelos faciais), uma conta de administrador criada, `backup.cmd` executado e o navegador em `http://127.0.0.1:8000`. Tenha uma segunda janela (anônima) para mostrar o cadastro de um usuário comum.

## O que dizer logo no início (30 s)

O EverLock é um **simulador** de controle de acesso: a porta, a trava, a energia e a rede são **virtuais**. O que é real é o software: contas, e-mail, reconhecimento facial com OpenCV, auditoria, alertas e cópia de segurança. Dizer isso cedo evita a pergunta "isso abre uma porta de verdade?".

## Sequência

| Min | O que mostrar | O que falar |
|---|---|---|
| 0:30 | Tela de **login** com a opção Cadastrar-se | Entra com e-mail ou usuário; cadastro exige e-mail válido |
| 1:30 | Cadastrar um usuário na janela anônima; mostrar o **link no terminal** (ou o e-mail, se o SMTP estiver configurado) | A conta só entra depois de confirmar o e-mail; sem aprovação manual |
| 2:30 | **Esqueci minha senha** na mesma conta | Link de 1 hora e uso único; a resposta é igual para quem existe ou não |
| 3:30 | **Identidades**: criar uma com consentimento e **Cadastrar rosto (câmera)** | Só o vetor numérico do rosto é guardado, cifrado; nenhuma imagem. Consentimento, retenção e exclusão |
| 5:00 | **Simulador > Reconhecimento facial**: seguir o giro sorteado; rosto cadastrado libera a trava; outro rosto mostra **Face não cadastrada** | Desafio de uso único, ligado à sessão e cancelável; a trava libera por 3 s virtuais, sem abrir a porta |
| 6:00 | **Entrar com o rosto** na tela de login | Pede um giro do rosto sorteado contra foto parada; sessão por rosto não cria administradores |
| 7:00 | **Falta de energia** e **falha de rede** nos cenários virtuais; comando remoto com prazo | Saída manual e chave continuam; comando vencido não é reexecutado |
| 8:30 | **Atividade**: filtrar por *Recusado* e **Baixar CSV** | Histórico com data real e tempo virtual; abre no Excel em português |
| 9:15 | Mostrar uma notificação no n8n (se configurado) e o `backup.cmd` | Alertas assinados, sem travar o app; cópia protegida por senha |

## Perguntas prováveis e respostas honestas

- **"O reconhecimento facial é seguro?"** É um protótipo. O desafio verifica um giro, mas não comprova presença real: vídeo gravado ou foto movimentada podem enganá-lo. Os limites ainda não foram calibrados com pessoas reais. Por isso a porta é virtual.
- **"Onde ficam as fotos?"** Em lugar nenhum: são analisadas na memória e descartadas. Guardamos só o vetor, cifrado com AES-256-GCM, e a chave fica separada do banco.
- **"E a LGPD?"** Biometria é dado sensível. O sistema tem termo de consentimento, revogação que apaga os vetores, retenção com exclusão automática e auditoria sem apelidos. Não é parecer jurídico.
- **"Funciona sem internet?"** Sim, exceto o envio de e-mail e do webhook. Sem e-mail configurado, o link aparece no terminal.
- **"Por que OpenCV?"** Instala com `pip` no Windows, roda na CPU e é gratuito; dlib e DeepFace exigiam compilador ou bibliotecas pesadas.
- **"O nobreak está integrado?"** Não. Ele alimenta o computador; o app só mostra o aviso de que o monitoramento é externo.

## Antes de subir ao palco

- Teste a câmera e a iluminação **no local**; luz de fundo derruba o reconhecimento.
- Registre a avaliação pelo [protocolo com imagens autorizadas](avaliacao-facial.md); não apresente testes com motor falso como precisão biométrica medida.
- Peça a outra pessoa para ensaiar os [cenários integrados](cenarios-integrados.md) e anotar as limitações encontradas.
- Cadastre o rosto de quem vai demonstrar (e só com autorização).
- Tenha um plano B: o **teste simulado** em Identidades funciona sem câmera.
- Feche outros programas que usem a câmera.
- Não deixe a senha do e-mail nem o `everlock.env` visíveis na tela.
