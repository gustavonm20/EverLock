# EverLock


[![CI](https://github.com/gustavonm20/EverLock/actions/workflows/ci.yml/badge.svg)](https://github.com/gustavonm20/EverLock/actions/workflows/ci.yml)

Simulador de controle de acesso desenvolvido em Python. Permite operar uma porta virtual, testar quedas de energia e consultar o histórico de eventos salvo em SQLite.

Tudo relacionado à porta, à trava e à chave é virtual. O grupo comprará um **nobreak pronto para alimentar o computador**, sem integração com o software. O EverLock não monitora carga/autonomia do equipamento e não controla uma fechadura física.

## Começar no Windows
É necessário ter **Python 3.13 ou superior** instalado e disponível no computador. A primeira instalação também precisa de internet para baixar as dependências.

1. Abra a pasta do projeto.
2. Execute `iniciar.cmd` com um duplo clique.
3. Aguarde a preparação do ambiente e acesse **http://127.0.0.1:8000** no navegador.
4. A tela inicial é de **login**, com a opção **Não tem conta? Criar conta**. Na primeira instalação, clique nessa opção para cadastrar o administrador. A senha precisa de no mínimo 6 caracteres, com letra maiúscula, minúscula, número e caractere especial; não há limite máximo nem senha padrão.

Depois da configuração inicial, a tela de entrada oferece **Criar conta**. O cadastro fica aguardando aprovação em **Conta > Pessoas com acesso**. Um administrador pode aprovar ou recusar; o cadastro não concede permissões administrativas. Para entrar no aplicativo, é necessário fazer login com uma conta ativa.

O iniciador prepara o ambiente Python local quando necessário e mantém o servidor funcionando na janela aberta. Para encerrar, use `Ctrl+C` nessa janela. Depois da instalação das dependências, a aplicação funciona sem acesso à internet.

Se preferir instalar manualmente, abra o PowerShell na pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps --no-build-isolation
.\.venv\Scripts\python.exe -m everlock
```

## Abrir no VS Code

1. Em **Arquivo > Abrir Pasta**, escolha a pasta que contém `iniciar.cmd` e `pyproject.toml`. No ZIP do GitHub, normalmente ela se chama `EverLock-main`; não selecione somente a pasta externa onde o ZIP foi extraído.
2. Instale a extensão **Python**, da Microsoft, sugerida pelo projeto.
3. No terminal integrado, execute `.\iniciar.cmd`. É necessário Python 3.13 ou superior.
4. Acesse `http://127.0.0.1:8000` no navegador.

Após a primeira preparação, também é possível executar com F5 usando a configuração **EverLock: simulador local**. Encerre o servidor anterior antes de iniciar outro. Se o VS Code pedir o interpretador, selecione `.venv\Scripts\python.exe`.

O pacote inclui todo o código-fonte, interface, testes e documentação desta etapa. A pasta `.venv` é criada no seu computador; não é distribuída. O histórico local também não acompanha o pacote.

## O que esta versão faz

- Mostra a porta e a trava virtuais em uma interface em português.
- O painel remoto simulado libera a entrada por três segundos virtuais e permite engatar a trava.
- A entrada local tem uma área de reconhecimento facial em preparação; ela ainda não reconhece pessoas nem libera a porta.
- Impede a abertura externa quando a trava está engatada.
- Permite fechar a porta, usar a chave simulada e demonstrar a saída interna.
- Registra ações e resultados no banco local.
- Simula bateria em Wh, consumo, recarga, economia, desligamento e recuperação.
- Permite pausar, acelerar ou avançar o tempo da porta e da bateria juntos.
- Alterna entre tema claro e escuro pelo botão de sol/lua, salvando a escolha no navegador.
- Mantém as regras no servidor: fechar a página não prolonga a liberação.
- Ao reiniciar, encerra a liberação anterior, recupera o cenário salvo e deixa o tempo pausado em 1×.
- Oferece login, contas de administrador/usuário, troca de senha e revogação imediata de sessões.
- Aplica permissões na API e registra a autoria das ações.
- Envia comandos remotos simulados com prazo real, confirmação, histórico e prevenção de duplicatas.
- Simula falhas independentes de internet e rede local, identificando observações antigas.
- Mostra **Status Nobreak** como uso externo, sem leituras inventadas; mantém cenários de energia virtual em uma seção de testes recolhida.

**Liberar a trava não abre a porta.** Depois da liberação, use a ação de entrada. Se o prazo acabar com a porta aberta, ela aguarda fechamento; o painel não deve indicar que está protegida.

A chave simulada e a saída interna representam métodos manuais. Seus botões alteram somente a simulação e continuam disponíveis com o dispositivo virtual desligado. Os três segundos de liberação usam o relógio virtual: pausar congela o prazo; acelerar também o encurta no tempo real.

## Demonstração rápida

1. Com a porta fechada e travada, tente abrir pelo lado externo: a ação deve ser negada.
2. Em **Conexão**, solicite **Liberar trava** e aguarde Executado; então abra a porta antes de três segundos virtuais.
3. Aguarde o fim da liberação: a porta permanece aberta, aguardando fechamento.
4. Feche a porta e observe a trava voltar ao estado engatado.
5. Experimente a saída interna e a chave simulada.
6. Confira o histórico e reinicie a aplicação para verificar a persistência.

Para demonstrar energia, abra **Status Nobreak > Cenários virtuais para testes**, pause o relógio, corte a alimentação virtual e avance seis horas. Observe o desligamento virtual, experimente a saída manual e restaure a alimentação. Avance três segundos para concluir a recuperação sem desbloqueio automático. Os parâmetros e cálculos estão em [Energia virtual](docs/energy.md).

## Limites desta entrega

Em **Conexão**, é possível liberar/travar a porta virtual, acompanhar cada comando e simular atrasos e interrupções. O prazo do comando usa segundos reais; os três segundos de liberação usam tempo virtual. Reconectar não executa comandos antigos. Veja o [roteiro de comunicação](docs/communication.md).

Ainda não há reconhecimento facial, cadastro biométrico, transporte remoto entre computadores ou integração com n8n. Essas funções estão no roteiro de desenvolvimento; não devem ser apresentadas como prontas. Driver e monitoramento do nobreak foram retirados do escopo.

O servidor fica restrito ao próprio computador, em `127.0.0.1`. O login protege o laboratório local; uma implantação na rede exigirá HTTPS e revisão da configuração. Use contas de demonstração, sem dados pessoais desnecessários. Esta etapa não coleta imagens.

O software funciona sem o nobreak e não exige hospedagem ou assinatura paga. A compra do nobreak é uma exceção ao escopo anterior sem custos; preço e autonomia ainda não foram definidos. Nenhuma bateria virtual mantém o computador ligado. O equipamento será usado apenas na alimentação do computador, e seu status deve ser consultado nele próprio. Ele também não garante internet durante a falta de energia.

## Dados e configuração

O banco é criado em `data/everlock.sqlite3`, na pasta do projeto. Ele guarda estado, eventos, contas, hashes de senhas e sessões. A pasta de dados fica fora do controle de versão. Faça cópias com o servidor parado e restrinja o acesso aos arquivos locais.

As configurações opcionais são variáveis de ambiente:

Defina-as no terminal quando necessário. O projeto não carrega arquivos `.env` automaticamente, e arquivos com esse prefixo são ignorados pelo Git para evitar a publicação acidental de configurações locais.

| Variável | Padrão | Uso |
|---|---|---|
| `EVERLOCK_PORT` | `8000` | Porta do servidor local |
| `EVERLOCK_DATA_DIR` | Pasta `data` do projeto | Diretório do banco; prefira um caminho absoluto |

Exemplo no PowerShell:

```powershell
$env:EVERLOCK_PORT = "8001"
.\.venv\Scripts\python.exe -m everlock
```

Nesse caso, acesse `http://127.0.0.1:8001`. Não altere o banco diretamente enquanto a aplicação estiver em execução.

## Verificações de desenvolvimento

Execute na pasta do projeto, depois da instalação:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

Os testes cobrem porta, energia, relógio, migração, recuperação, autenticação, papéis, revogação, comandos, conflitos e falhas de conexão. Também verificam que o aviso do nobreak não apresenta a bateria virtual como leitura real. Os testes do módulo antigo de observações permanecem isolados; ele não é usado pelo aplicativo. A verificação visual no navegador complementa esses testes.

## Documentação

- [Arquitetura](docs/architecture.md)
- [Planejamento e critérios de aceite](docs/planning.md)
- [Energia virtual e roteiro de demonstração](docs/energy.md)
- [Contas, permissões e recuperação de acesso](docs/accounts.md)
- [Comandos remotos e falhas de conexão](docs/communication.md)
- [Nobreak externo: uso e limites](docs/ups.md)
- [API local](docs/api.md)
- [Etapas de desenvolvimento](docs/roadmap.md)
- [Estado atual](docs/status.md)
- [Decisões do projeto](docs/decisions.md)

## Colaboração

O [espaço do EverLock no Notion](https://app.notion.com/p/EverLock-3e8e2dde06ab809c893fcbd6a4958ff8) reúne o planejamento anterior, as 18 tarefas, Kanban, checklists, guia do grupo, cenários e decisões. O GitHub concentra [issues](https://github.com/gustavonm20/EverLock/issues), revisão de código, testes e o [roadmap](https://github.com/users/gustavonm20/projects/3). Os quadros são atualizados por entrega; ainda não há sincronização automática.

Consulte [CONTRIBUTING.md](CONTRIBUTING.md) antes de alterar o código e [SECURITY.md](SECURITY.md) para relatos de segurança. Este repositório não distribui imagens faciais, bancos locais ou credenciais.

.
