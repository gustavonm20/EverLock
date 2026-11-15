# Atualização para a 0.18.0 (local)

A 0.18.0 acrescenta o ponto de acesso facial, o acesso pela porta com o próprio rosto e
o acabamento visual. Ela **não foi publicada** no GitHub; a base publicada é a 0.16.1.

## Antes de atualizar uma instalação com dados

1. Feche o EverLock e faça uma cópia: `.\.venv\Scripts\python.exe -m everlock backup --senha`.
2. Guarde o arquivo `.elbak` e a senha fora do computador.
3. Substitua o código e rode `.\iniciar.cmd` normalmente.

## O que muda no banco

- Migração **aditiva** da versão 2 para a 3, feita uma vez ao iniciar: novas colunas
  `identities.account_id` e `identities.subject_consent_by` e um índice único parcial
  (uma identidade por conta). Nenhum dado existente é alterado ou removido.
- Identidades antigas ficam sem vínculo e continuam funcionando como antes.
- Depois de migrado, o banco **não abre** em versões anteriores (elas recusam banco de
  versão futura). Para voltar à 0.16.1, restaure a cópia feita no passo 1.

## O que muda no uso

- Capturas recusadas, cancelamentos, desafios vencidos e motor indisponível agora
  aparecem em **Atividade** com origem *Reconhecimento*. Se o webhook opcional estiver
  no nível `warning`, recusas passam a gerar mais alertas; cancelamentos são `info`.
- O teste simulado sem câmera continua disponível, mas fica em "Laboratório: teste sem
  câmera (simulado)" dentro do ponto de acesso.
- Para vincular uma pessoa, crie (ou edite) a identidade em **Identidades** escolhendo a
  conta. A pessoa conclui o aceite e o cadastro em **Conta › Meu acesso pela porta**.

## Verificação automatizada

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/browser -q
```

Opcional: com os modelos baixados, o teste do pipeline OpenCV real com quadros gerados
por código (sem pessoas) roda definindo a pasta dos modelos:

```powershell
$env:EVERLOCK_TEST_MODELS_DIR = "$PWD\data\models"
.\.venv\Scripts\python.exe -m pytest tests/test_face_access_flow.py -q
```

Esses testes comprovam a integração reconhecimento → autorização → trava virtual. Eles
não medem precisão facial, desempenho de câmera real nem prova de vida.
