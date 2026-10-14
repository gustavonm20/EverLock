# Testes de interface no navegador

Esta bateria pequena abre o EverLock de verdade em um navegador sem janela. O objetivo é
verificar login, permissões e o ciclo de vida do diagnóstico, incluindo uma resposta que
chega depois de sair da página ou encerrar a sessão.

Os oito testes usam um servidor HTTP em `127.0.0.1`, porta disponível e banco temporário
novo por teste. As contas são fictícias. SMTP e webhook são explicitamente desativados e
o motor facial é substituído por um motor indisponível. O teste de consentimento
simula a disponibilidade somente na resposta da interface e usa um `MediaStream`
vazio: não abre dispositivo nem produz imagens pessoais. O navegador também usa um
perfil temporário separado do perfil habitual.

## Preparar e executar

Na raiz do projeto, com o ambiente de desenvolvimento ativo:

```powershell
python -m pip install -r requirements.lock.txt -r requirements-browser.txt
python -m pip install -e . --no-deps --no-build-isolation
python -m playwright install chromium
python -m pytest tests/browser -q
```

Em Linux/CI, `python -m playwright install --with-deps chromium` instala também as
bibliotecas de sistema necessárias. A versão do Playwright está fixada no arquivo de
dependências; o comando instala o Chromium correspondente.

O pacote e o navegador são ferramentas opcionais de desenvolvimento e não fazem parte
das dependências de funcionamento do simulador. A execução habitual `python -m pytest -q`
ignora `tests/browser`; a chamada explícita acima executa esta bateria. Uma instalação
incompleta gera erro, em vez de apresentar testes ignorados como uma execução aprovada.

Para aproveitar uma instalação local do Chrome ou Edge, é possível escolher o canal:

```powershell
$env:EVERLOCK_TEST_BROWSER_CHANNEL = "chrome"  # ou "msedge"
python -m pytest tests/browser -q
Remove-Item Env:EVERLOCK_TEST_BROWSER_CHANNEL
```

O canal utiliza um perfil temporário do navegador, sem abrir o perfil pessoal. No CI,
deixe essa variável ausente para utilizar o Chromium instalado pelo Playwright.

## O que está coberto

1. Administrador entra pela interface, abre o diagnóstico, vê as verificações da API
   e atualiza a consulta.
2. Usuário comum não vê o atalho administrativo; tentar abrir `#diagnostico` redireciona
   para o simulador, e a API também recusa a leitura.
3. Uma sessão que expirou é recusada pelo servidor; a interface mostra o login e remove
   os resultados administrativos já exibidos.
4. Uma resposta antiga do diagnóstico não volta a preencher a página depois de navegar
   para outra seção ou sair da conta. O teste atrasa a entrega de uma resposta real e
   ignora intencionalmente o cancelamento do transporte para exercitar essa condição.

5. Menu, navegação, Escape e ausência de rolagem horizontal em 1440 × 1000 e
   390 × 844; capturas das páginas Visão geral, Identidades e Configuração.
6. Falha ao aplicar filtros invalida o cursor anterior; “Carregar mais” não mistura
   páginas de consultas diferentes.
7. Alterar filtros durante uma exportação impede que a resposta antiga restaure
   seu cursor no novo CSV.
8. Desmarcar o consentimento enquanto a resposta chega não liga a câmera; o botão
   de preparação fica desativado quando a câmera sintética já está em uso.

Os testes aguardam respostas e estados da interface, sem pausas fixas para sincronizar
ações. Erros JavaScript não tratados fazem o teste falhar. Não há snapshots de pixels;
alterações cosméticas que preservem o comportamento não precisam alterar a bateria.

Isso não valida reconhecimento de pessoas, precisão biométrica, resistência a fotos ou
vídeos, envio real de e-mail, n8n, equipamento de alimentação ou a apresentação humana.
Esses aceites continuam no [planejamento](planning.md).

Referências: [biblioteca Python do Playwright](https://playwright.dev/python/docs/library),
[assertivas com espera automática](https://playwright.dev/python/docs/test-assertions) e
[controle de tráfego para testes](https://playwright.dev/python/docs/network).
