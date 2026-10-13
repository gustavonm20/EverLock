# Trabalhando no EverLock

## Referências

- Código e testes descrevem o comportamento atual. Consulte `docs/status.md`,
  `docs/planning.md` e `docs/decisions.md` para entregas, aceites e decisões.
- Preserve a arquitetura local FastAPI/SQLite e a interface HTML/CSS/JavaScript.
  Evolua os módulos existentes; justifique novas dependências pelo benefício concreto.
- Trabalhe em incrementos pequenos, com objetivo e critério de conclusão claros.
  Preserve alterações locais do usuário e use uma branch por entrega.

## Regras do produto

- O controlador decide a atuação. Liberar a trava por três segundos virtuais não abre
  a porta. Saída interna e chave simuladas continuam disponíveis sem energia virtual.
- Sessões e comandos usam tempo real; a simulação tem relógio próprio. Reinício e
  reconexão não podem repetir comandos ou liberações anteriores.
- Porta, trava e sensores são virtuais. O nobreak apenas alimenta o computador;
  não adicionar drivers, telemetria física ou leituras inventadas.
- Preserve consentimento, revogação, retenção e cifra. Nunca versionar bancos,
  credenciais, chaves, imagens pessoais ou vetores biométricos.
- Notificações são opcionais e não autorizam acesso. Disponibilidade de biblioteca
  ou configuração não prova precisão facial, entrega externa ou funcionamento real.

## Verificação e publicação

- Execute `python -m ruff check src tests scripts` e os testes relevantes à mudança.
  A suíte geral usa `python -m pytest -q`; os testes de navegador são separados,
  conforme `docs/testes-interface.md`. Amplie testes quando o risco justificar.
- Para alterações visuais, confira a interface em computador e celular, com dados
  de teste isolados. Não use dados pessoais para substituir testes sintéticos.
- Registre o que mudou, como foi validado e limitações reais em `docs/status.md`.
  Use os modelos de issue/PR existentes. Atualize GitHub e Notion quando autorizado,
  respeitando as proteções da branch principal e os aceites ainda pendentes.

## Pendências adiadas pelo responsável em 03/10/2026

Continuam pendentes até uma orientação posterior: consentimento pessoal das
identidades, avaliação/calibração facial real, ensaio com câmera real, demonstração
por outra pessoa, validação operacional de instalação/e-mail/backup, continuidade
com nobreak e validação de n8n/relatórios periódicos. Implementações e testes
sintéticos não encerram esses aceites. Veja `docs/pendencias.md`.
