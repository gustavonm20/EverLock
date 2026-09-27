# Contas e permissões locais

Na primeira abertura, o navegador pede a criação do administrador. Não há senha padrão ou conta pré-cadastrada. Usuários têm 3 a 32 caracteres ASCII (letras, números, ponto, hífen ou sublinhado), normalizados em minúsculas.

## Cadastro e senha

Após a configuração inicial, **Não tem conta? Criar conta** abre o formulário com usuário, senha e confirmação. Novos cadastros ficam pendentes, sem sessão nem acesso ao aplicativo. Em **Conta > Pessoas com acesso**, o administrador aprova ou recusa a solicitação. A aprovação concede papel de usuário; somente um administrador pode alterar papéis posteriormente. Recusar mantém a conta desativada, sem apagar o histórico.

A política solicitada pelo grupo exige **no mínimo 6 caracteres, sem limite máximo**, contendo ao menos uma letra maiúscula, uma minúscula, um número e um caractere especial. Pontuação e símbolos, como `.`, `?`, `@` e `$`, contam como especiais; espaço sozinho não conta. A senha não é truncada nem tem espaços removidos. A mesma regra vale no navegador, na API, na criação administrativa, na troca e na recuperação por terminal.

O login verifica a senha existente sem reaplicar a regra de criação: contas anteriores continuam funcionando. Ao escolher uma nova senha, passam a seguir a regra atual. O usuário e as senhas não aparecem em mensagens de erro de validação como conteúdo original enviado.

## Papéis

| Operação | Usuário | Administrador |
|---|---|---|
| Consultar porta, energia e disponibilidade do nobreak | Sim | Sim |
| Liberar/encerrar liberação, entrar, fechar e demonstrar saída interna | Sim | Sim |
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

O cadastro aceita até cinco solicitações por cliente em cinco minutos reais e o laboratório suporta até 100 contas. A API de cadastro não aceita `role`, `active` ou outros campos adicionais. Não há envio de e-mail, serviço externo ou senha salva em texto aberto.

Contas e eventos administrativos têm tabelas separadas do estado da porta. Eventos de ações identificam o usuário; eventos automáticos mantêm origem de sistema. A verificação de sessão e a ação compartilham a mesma trava de concorrência da revogação.

## Recuperar um administrador

Encerre o servidor e faça uma cópia do banco com ele parado. Na pasta do projeto:

```powershell
.\.venv\Scripts\python.exe -m everlock.recover_admin nome_do_administrador
```

O terminal solicita e confirma a nova senha sem exibi-la. O comando só recupera um administrador ativo existente, revoga suas sessões e registra a recuperação. Respeita `EVERLOCK_DATA_DIR`. Acesso aos arquivos locais é uma fronteira de confiança: quem controla o computador e seu banco pode recuperar contas.

## API

`GET /api/auth/session` informa se falta o primeiro administrador e a sessão atual. `POST /setup` e `POST /login` recebem `username` e `password`; `/logout` encerra a sessão. Os caminhos a seguir também têm prefixo `/api/auth`:

- `POST /register`: cadastro público local com `username`, `password` e `confirm_password`; retorna 201 e aguarda aprovação, sem iniciar sessão.
- `GET/POST /users`: listar/criar (admin), incluindo `role` na criação.
- `PATCH /users/{id}`: definir `role` e `active` (admin), revogando sessões.
- `POST /password`: `current_password` e `new_password`; exige sessão.
- `GET /events`: últimos 50 eventos administrativos (admin).

Dados inválidos retornam 422, falta de sessão 401, falta de papel 403, conflito 409 e limite de tentativas 429. A aplicação continua local; cadastro facial e políticas por horário ainda estão planejados.
