# EverLock

[![CI](https://github.com/gustavonm20/EverLock/actions/workflows/ci.yml/badge.svg)](https://github.com/gustavonm20/EverLock/actions/workflows/ci.yml)

Simulador de controle de acesso desenvolvido em Python. Esta primeira entrega permite operar uma porta virtual pelo navegador e consultar o histórico de eventos salvo em SQLite.

Tudo relacionado à porta, à trava e à chave é virtual. Não há integração com fechaduras físicas.

## Começar no Windows

É necessário ter **Python 3.13 ou superior** instalado e disponível no computador. A primeira instalação também precisa de internet para baixar as dependências.

1. Abra a pasta do projeto.
2. Execute `iniciar.cmd` com um duplo clique.
3. Aguarde a preparação do ambiente e acesse **http://127.0.0.1:8000** no navegador.

O iniciador prepara o ambiente Python local quando necessário e mantém o servidor funcionando na janela aberta. Para encerrar, use `Ctrl+C` nessa janela. Depois da instalação das dependências, a aplicação funciona sem acesso à internet.

Se preferir instalar manualmente, abra o PowerShell na pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps --no-build-isolation
.\.venv\Scripts\python.exe -m everlock
```

## Abrir no VS Code

1. Extraia o ZIP e abra a pasta `everlock` em **Arquivo > Abrir Pasta**.
2. Instale a extensão **Python**, da Microsoft, sugerida pelo projeto.
3. No terminal integrado, execute `.\iniciar.cmd`. É necessário Python 3.13 ou superior.
4. Acesse `http://127.0.0.1:8000` no navegador.

Após a primeira preparação, também é possível executar com F5 usando a configuração **EverLock: simulador local**. Encerre o servidor anterior antes de iniciar outro. Se o VS Code pedir o interpretador, selecione `.venv\Scripts\python.exe`.

O pacote inclui todo o código-fonte, interface, testes e documentação desta etapa. A pasta `.venv` é criada no seu computador; não é distribuída. O histórico local também não acompanha o pacote.

## O que esta versão faz

- Mostra a porta e a trava virtuais em uma interface em português.
- Libera a entrada por três segundos e permite encerrar a liberação.
- Impede a abertura externa quando a trava está engatada.
- Permite fechar a porta, usar a chave simulada e demonstrar a saída interna.
- Registra ações e resultados no banco local.
- Mantém as regras no servidor: fechar a página não prolonga a liberação.
- Ao reiniciar, encerra a liberação anterior e recupera a última posição registrada da porta.

**Liberar a trava não abre a porta.** Depois da liberação, use a ação de entrada. Se o prazo acabar com a porta aberta, ela aguarda fechamento; o painel não deve indicar que está protegida.

A chave simulada e a saída interna representam métodos manuais. Seus botões alteram somente a simulação.

## Demonstração rápida

1. Com a porta fechada e travada, tente abrir pelo lado externo: a ação deve ser negada.
2. Libere a entrada e abra a porta antes de três segundos.
3. Aguarde o fim da liberação: a porta permanece aberta, aguardando fechamento.
4. Feche a porta e observe a trava voltar ao estado engatado.
5. Experimente a saída interna e a chave simulada.
6. Confira o histórico e reinicie a aplicação para verificar a persistência.

## Limites desta entrega

Ainda não há login, cadastro de pessoas, reconhecimento facial, bateria simulada, falhas de conexão ou integração com n8n. Essas funções estão no roteiro de desenvolvimento; botões ou indicadores desta versão não devem ser apresentados como implementação dessas etapas.

O servidor fica restrito ao próprio computador, em `127.0.0.1`. Como ainda não há autenticação, não o exponha à rede nem à internet. Esta etapa não exige coleta de imagens ou outros dados pessoais.

Não é necessário comprar hardware ou contratar hospedagem para executar a base em um computador disponível. O projeto continua dependendo desse computador e de sua alimentação elétrica; nenhuma bateria virtual o manterá ligado.

## Dados e configuração

O banco é criado em `data/everlock.sqlite3`, na pasta do projeto. Ele guarda o estado e os eventos da simulação. A pasta de dados fica fora do controle de versão.

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

Os testes devem cobrir as regras da porta, o prazo de liberação, as rotas e a recuperação do estado. A verificação visual no navegador complementa esses testes.

## Documentação

- [Arquitetura](docs/architecture.md)
- [API local](docs/api.md)
- [Etapas de desenvolvimento](docs/roadmap.md)
- [Estado atual](docs/status.md)
- [Decisões do projeto](docs/decisions.md)

## Colaboração

O trabalho futuro é organizado nas [issues](https://github.com/gustavonm20/EverLock/issues), nos [marcos](https://github.com/gustavonm20/EverLock/milestones) e no projeto [EverLock · Roadmap](https://github.com/users/gustavonm20/projects/3). O projeto contém Kanban, prioridades e uma visão de roadmap.

Consulte [CONTRIBUTING.md](CONTRIBUTING.md) antes de alterar o código e [SECURITY.md](SECURITY.md) para relatos de segurança. Este repositório não distribui imagens faciais, bancos locais ou credenciais.
