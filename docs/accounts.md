# Contas e permissões locais

A primeira tela é sempre o **login**, com a opção **Não tem conta? Cadastrar-se**. O cadastro só aparece ao selecionar essa opção; quando não existe conta, ele prepara o primeiro administrador. Não há senha padrão ou conta pré-cadastrada. Usuários têm 3 a 32 caracteres ASCII (letras, números, ponto, hífen ou sublinhado), normalizados em minúsculas. O login aceita **e-mail ou usuário** e a senha, sem diferenciar maiúsculas de minúsculas no identificador.

## Cadastro e senha

Após a configuração inicial, **Cadastrar-se** abre o formulário com usuário, **e-mail válido**, senha e confirmação. A conta é **criada na hora**, sem aprovação de administrador, com papel de usuário e ainda sem poder entrar: o EverLock envia uma mensagem para o e-mail informado e a conta só entra depois que o link é aberto (veja [E-mail de confirmação](#e-mail-de-confirmação)). No cadastro, a pessoa escolhe o **tipo de conta**: *Usuário* (padrão) ou *Administrador*. Escolher administrador exige um **código de convite** gerado por outro administrador (veja [Convites de administrador](#convites-de-administrador)); sem ele, o cadastro é recusado e nenhum privilégio é concedido. Somente um administrador altera papéis depois. O primeiro administrador e as contas criadas por administradores em **Conta > Pessoas com acesso** não precisam confirmar: quem cria responde pelo e-mail. Contas antigas, sem e-mail, continuam entrando pelo usuário.

A política solicitada pelo grupo exige **no mínimo 6 caracteres, sem limite máximo**, contendo ao menos uma letra maiúscula, uma minúscula, um número e um caractere especial. Pontuação e símbolos, como `.`, `?`, `@` e `$`, contam como especiais; espaço sozinho não conta. A senha não é truncada nem tem espaços removidos. A mesma regra vale no navegador, na API, na criação administrativa, na troca e na recuperação por terminal.

O login verifica a senha existente sem reaplicar a regra de criação: contas anteriores continuam funcionando. Ao escolher uma nova senha, passam a seguir a regra atual. O usuário e as senhas não aparecem em mensagens de erro de validação como conteúdo original enviado.

## Papéis

| Operação | Usuário | Administrador |
|---|---|---|
| Consultar porta, energia virtual e aviso de nobreak externo | Sim | Sim |
| Comandos remotos, encerrar liberação, entrar, fechar e saída interna | Sim | Sim |
| Liberação direta pela API de testes locais (`/api/actions`, `unlock`) | Não | Sim |
| Demonstrar chave de acesso | Não | Sim |
| Preparar cenário e controlar energia/relógio | Não | Sim |
| Consultar histórico da porta e de contas | Não | Sim |
| Criar contas, mudar papéis, desativar/reativar | Não | Sim |
| Trocar a própria senha com confirmação da atual | Sim | Sim |

Permissões são verificadas na API, não só nos botões. Alterar papel/ativação ou senha revoga as sessões da conta. Não é permitido remover o último administrador ativo. Uma nova sessão encerra a anterior da mesma conta; para demonstração em dois navegadores simultâneos, use contas diferentes.

A saída interna é um comportamento manual do domínio virtual e continua possível para uma sessão autorizada quando a energia virtual acaba. O login controla o laboratório de software, não uma saída física. Desativar uma conta não fecha automaticamente uma porta aberta.

## Sessão e senhas

Hash de senha com scrypt N=32768, r=8, p=3 e salt aleatório por senha, usando a biblioteca padrão do Python. A escolha evita dependência adicional e segue uma das configurações da [referência OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html); não representa certificação.

O navegador recebe um identificador aleatório de 32 bytes em cookie HttpOnly e SameSite=Strict. Apenas seu hash é salvo no SQLite. Prazo absoluto de oito horas reais; o relógio virtual não estende nem reduz a sessão. Logout a revoga no servidor. O cookie usa Secure quando há HTTPS; a execução atual é HTTP restrita a loopback, sem autorização para exposição à rede. A futura implantação remota exigirá HTTPS e revisão do modelo de acesso.

Cinco falhas por conta ou vinte por cliente em cinco minutos reais bloqueiam novas tentativas nessa janela. Falhas persistem no banco entre reinícios. Proteções de origem/JSON complementam a sessão. Senhas, tokens e entradas inválidas não são devolvidos no histórico ou em erros de validação.

O cadastro aceita até cinco solicitações por cliente em cinco minutos reais e o laboratório suporta até 100 contas. A API aceita `role` e `invite_code` conforme a política de convites; `active` e campos desconhecidos são recusados. O envio de e-mail depende da configuração SMTP; sem ela, o link aparece no terminal. Senhas nunca são salvas em texto aberto.

Contas e eventos administrativos têm tabelas separadas do estado da porta. Eventos de ações identificam o usuário; eventos automáticos mantêm origem de sistema. A verificação de sessão e a ação compartilham a mesma trava de concorrência da revogação.

## Recuperar um administrador

Encerre o servidor e faça uma cópia do banco com ele parado. Na pasta do projeto:

```powershell
.\.venv\Scripts\python.exe -m everlock.recover_admin nome_do_administrador
```

O terminal solicita e confirma a nova senha sem exibi-la. O comando só recupera um administrador ativo existente, revoga suas sessões e registra a recuperação. Respeita `EVERLOCK_DATA_DIR`. Acesso aos arquivos locais é uma fronteira de confiança: quem controla o computador e seu banco pode recuperar contas.

## API

`GET /api/auth/session` informa se falta o primeiro administrador e a sessão atual. `POST /login` recebe `identifier` (e-mail ou usuário) e `password`; `POST /setup` recebe `username`, `email` e `password`; `/logout` encerra a sessão. Os caminhos a seguir também têm prefixo `/api/auth`:

- `POST /register`: cadastro público local com `username`, `email`, `password` e `confirm_password`; retorna 201, cria a conta e envia o e-mail de confirmação (`delivery`: `email` ou `console`). Se o envio falhar, o cadastro é desfeito (503) e usuário e e-mail voltam a ficar livres.
- `POST /register` também aceita `role` (`user` ou `admin`) e `invite_code`: `admin` exige código válido (403 se inválido, expirado ou usado; 422 se ausente); `user` não aceita código.
- `GET/POST /invites` e `DELETE /invites/{id}` (admin): listar convites abertos, gerar um novo (o código só aparece na resposta da criação) e revogar.
- `POST /confirm-email`: recebe o `token` do link e confirma o e-mail; o token vale 24 horas e só uma vez.
- `POST /resend-confirmation`: recebe `identifier` e `password` e envia um novo link para quem prova ser dono da conta.
- `GET/POST /users`: listar/criar (admin), incluindo `role` na criação.
- `PATCH /users/{id}`: definir `role` e `active` (admin), revogando sessões.
- `POST /password`: `current_password` e `new_password`; exige sessão.
- `GET /events`: últimos 50 eventos administrativos (admin).

Dados inválidos retornam 422, falta de sessão 401, falta de papel 403, conflito 409 e limite de tentativas 429. A aplicação continua local. Identidades biométricas, consentimento e horários de acesso são independentes das contas; veja [identities.md](identities.md).

## E-mail de confirmação

O link do e-mail é `http://127.0.0.1:8000/#confirmar=<token>`. O token fica depois do `#` (fragmento), que o navegador não envia ao servidor, e a página o remove do endereço ao usá-lo. O banco guarda apenas o hash do token.

As credenciais de envio **nunca ficam no código nem no GitHub**. Copie `everlock.env.example` para `everlock.env` (ignorado pelo Git) e preencha `EVERLOCK_SMTP_HOST`, `EVERLOCK_SMTP_PORT`, `EVERLOCK_SMTP_USER` e `EVERLOCK_SMTP_PASSWORD`. Variáveis de ambiente do sistema têm prioridade sobre o arquivo. O envio usa STARTTLS (porta 587) ou SSL (465).

- **Gmail:** o SMTP não aceita a senha normal da conta. Ative a verificação em duas etapas e crie uma *senha de app* em https://myaccount.google.com/apppasswords.
- **Sem configuração:** o app funciona igual, mas o link de confirmação é exibido no terminal do servidor (o terminal avisa na inicialização). Serve para demonstrações locais; a API nunca devolve o link.
- Um e-mail sintaticamente válido não prova que exista: quem prova é a confirmação. Por isso a conta não entra antes dela.

## Esqueci minha senha

Na tela de login, digite o e-mail ou o usuário no campo e clique em **Esqueci minha senha**. Se existir uma conta ativa, aprovada e com e-mail confirmado, o EverLock envia um link (`#redefinir=<token>`) que vale **1 hora** e **uma única vez**; o banco guarda só o hash. Ao abri-lo, a tela pede a nova senha (mesma política de senhas) e a confirmação.

- **Resposta idêntica para qualquer identificador.** A mensagem não diz se a conta existe, e o e-mail é enviado depois da resposta, para o tempo de resposta também não revelar. Contas desativadas ou sem e-mail confirmado não recebem link.
- **Limite:** 5 pedidos a cada 5 minutos por computador.
- **Ao redefinir:** a senha antiga deixa de valer, **todas as sessões da conta são encerradas**, o bloqueio por tentativas erradas é limpo e um novo pedido invalida o link anterior. O rosto cadastrado, se houver, continua valendo.
- **Sem e-mail configurado**, o link aparece no terminal do servidor (veja [E-mail de confirmação](#e-mail-de-confirmação)). Falha no envio é registrada no histórico, sem revelar nada ao navegador.
- Quem controla o e-mail da conta controla a senha dela: proteja a caixa de entrada.

## Entrar com o rosto

Qualquer conta pode cadastrar o próprio rosto em **Conta > Entrar com o rosto** (senha atual + concordância com o termo + 5 fotos) e depois usar **Entrar com o rosto** na tela de login. A senha continua valendo. Detalhes, limites e riscos em [facial-recognition.md](facial-recognition.md#entrar-no-aplicativo-com-o-rosto-incremento-07). Um administrador pode remover o rosto de uma conta; desativar a conta bloqueia também a entrada pelo rosto. Administradores também podem entrar pelo rosto, mas a sessão aberta assim **não gera convites, não cria administradores e não promove contas**: essas ações respondem 403 `password_required` até a pessoa entrar com a senha. Cada recusa vai para o histórico (`face_session_restricted`).

## Convites de administrador

Deixar qualquer pessoa marcar "Administrador" num formulário público entregaria o controle do laboratório (contas, identidades, cenários) a quem apenas conhece a tela. Por isso a escolha existe, mas é protegida por um convite:

1. Um administrador abre **Conta > Pessoas com acesso > Convites de administrador** e clica em **Gerar código de convite**.
2. O código (`XXXX-XXXX-XXXX`, sem caracteres ambíguos como 0/O e 1/I) aparece **uma única vez**; o banco guarda só o hash. Vale 24 horas e serve para um único cadastro.
3. A pessoa escolhe *Administrador* no cadastro e digita o código (com ou sem hífens, em qualquer caixa). Ela ainda precisa confirmar o e-mail.
4. Há no máximo 10 convites abertos; convites abertos podem ser revogados. Se o envio do e-mail falhar e o cadastro for desfeito, o convite volta a valer.

Recusas e criações de convite entram no histórico de contas, sem o código. Alternativas descartadas: (a) papel escolhido livremente, por permitir escalada de privilégio; (b) pedido de administrador aprovado depois, por exigir que um administrador esteja presente e ainda dar à pessoa uma conta comum no meio do caminho. Para demonstrações, o administrador também pode criar a conta já com o papel desejado, ou promover alguém em **Salvar papel**.
