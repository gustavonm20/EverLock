# Reconhecimento facial

Esta é a base do reconhecimento facial do EverLock (incremento 0.6). Sim: é feito com **OpenCV**, usando dois modelos pequenos e gratuitos do projeto OpenCV Zoo.

> **Leia antes de confiar nele.** O reconhecimento aponta *quem parece estar na imagem*; ele **não prova que a pessoa está viva**. Uma foto ou vídeo de um rosto cadastrado, mostrado à câmera, pode enganar este sistema. Por isso ele serve ao laboratório com porta *virtual*, não para proteger uma porta real. Veja [Limitações](#limitações).

## Por que OpenCV (YuNet + SFace)

| Opção | Resultado |
|---|---|
| **OpenCV: YuNet + SFace (escolhida)** | Instala com um `pip`, roda na CPU, sem TensorFlow/PyTorch e sem compilar nada no Windows. Modelos de 0,2 MB e 37 MB. Precisão boa para um laboratório. |
| Haar cascade / LBPH (OpenCV antigo) | Só detecta ou reconhece com pouca precisão; muitas falsas aceitações. Descartado. |
| `face_recognition` / dlib | Boa precisão, mas exige CMake e compilador C++ no Windows: a instalação costuma quebrar. |
| DeepFace / InsightFace | Mais precisos, porém pesados (TensorFlow ou ONNX grandes) e baixam modelos por conta própria. |

O desenho isola o motor atrás de uma interface pequena (`FaceEngine.read(imagem) -> vetor`). Trocar o OpenCV por outro motor mexe em um arquivo (`faces.py`), não nas regras de acesso.

## Como funciona

```
Navegador (câmera)            Servidor local
 getUserMedia ──foto JPEG──►  faces.py (OpenCV)           biometrics.py
                               1 rosto? nítido? grande?    vetor de 128 números
                               └────────► vetor ─────────► cifra AES-256-GCM
                                                              │ cadastro
                                                              ▼
 recognition.py: compara o vetor com os cadastrados (cosseno) ──► identidade candidata
 identities.evaluate(): consentimento, retenção, ativa, horário ──► autorizada?
 controller: dispositivo ligado e porta fechada? ──► libera a trava por 3 s (a porta NÃO abre)
```

1. **Detecção (YuNet):** exige exatamente um rosto, com pelo menos 80 px e nota de detecção ≥ 0,90.
2. **Qualidade:** recusa imagem borrada (variância do Laplaciano do rosto alinhado).
3. **Vetor (SFace):** o rosto é alinhado e vira 128 números. A imagem é descartada.
4. **Comparação:** similaridade de cosseno com todos os vetores cadastrados; vale a melhor de cada identidade.
5. **Decisão:** o rosto só *indica* uma identidade. Quem autoriza é `evaluate()` (a mesma regra do teste simulado). Depois, o controlador aplica as regras da porta.

## Instalação (uma vez)

1. `.\iniciar.cmd` instala as bibliotecas (inclui o OpenCV, cerca de 50 MB).
2. Os modelos são baixados **sozinhos** pelo `iniciar.cmd` (cerca de 39 MB, só na primeira vez, com verificação de tamanho e SHA-256). Se a internet falhar, o app abre normalmente sem o reconhecimento e avisa. Para tentar de novo:
   ```powershell
   .\.venv\Scripts\python scripts\baixar_modelos.py
   ```
   Eles ficam em `data/models/` (pasta ignorada pelo Git).
3. Reinicie o EverLock. Em **Simulador > Reconhecimento facial**, o painel passa a dizer *Reconhecimento facial por câmera*. Se faltar algo, ele mostra o motivo.
4. (Opcional) confira o motor com fotos suas, sem abrir o app:
   ```powershell
   .\.venv\Scripts\python scripts\testar_rosto.py foto1.jpg foto2.jpg foto_de_outra_pessoa.jpg
   ```

A câmera funciona em `http://127.0.0.1:8000` porque o navegador trata esse endereço como seguro. O Chrome e o Edge pedem permissão na primeira vez.

## Cadastro (Identidades > Cadastrar rosto)

- Exige a identidade criada com o **termo de consentimento atual** (versão 2026-10-01). Identidades criadas com o termo antigo precisam ser excluídas e criadas de novo, porque aquele termo não cobria o vetor facial.
- Tira **5 fotos** em cerca de 5 segundos, com instruções (de frente, leve giro para cada lado). Precisa de pelo menos 3 boas.
- As fotos têm de ser da **mesma pessoa** (cada vetor deve parecer com os outros). Se não forem, o cadastro é recusado.
- O mesmo rosto **não pode** estar em duas identidades (evita fantasmas e ambiguidade).
- Refazer o cadastro substitui as amostras anteriores. A tela só aceita administradores.

## Reconhecimento

- **Desafio de movimento:** antes de comparar o rosto para liberar a porta, o servidor sorteia um giro curto para a esquerda ou direita. O desafio vale uma vez e expira em 45 segundos. A foto inicial precisa estar de frente, alguma das fotos seguintes precisa mostrar o giro pedido e o rosto precisa continuar sendo o mesmo.
- **Cancelamento e sessão:** o desafio pertence à sessão que o pediu. Desligar a câmera, trocar de página ou aba solicita seu encerramento; novo desafio da mesma sessão invalida o anterior. A sessão e o prazo são rechecados depois da análise, imediatamente antes de liberar a trava. Uma resposta tardia não altera a tela de outra operação.
- **Limite de similaridade: 0,45.** A documentação do SFace cita 0,363 como ponto de equilíbrio; para acesso, o padrão é mais rígido (menos falsas aceitações, mais falsas rejeições).
- **Margem de ambiguidade: 0,05.** Se o rosto passa do limite para duas identidades quase ao mesmo tempo, é recusado (`ambiguous`).
- **Bloqueio:** 5 reconhecimentos sem sucesso em 60 s bloqueiam novas tentativas por até 60 s (`rate_limited`), inclusive para o rosto certo. Problemas de captura (sem rosto, borrado, dois rostos) **não** contam: não são tentativas de acesso.
- Reconhecido mas não autorizado (horário, desativada, consentimento) mantém a trava engatada e registra a identidade e o motivo.
- Autorizado: libera a trava por 3 segundos virtuais. **A porta não abre sozinha.** Eventos citam só `Identidade #n` e a similaridade.

> Todos os limites ficam em `FaceSettings` (`recognition.py`) e `faces.py` e são **provisórios**. O [protocolo de avaliação](avaliacao-facial.md) usa `scripts/avaliar_rostos.py` para medir erros e latência com conjuntos autorizados e separados. `scripts/testar_rosto.py` ajuda no diagnóstico do giro, mas não substitui esse levantamento.

## Privacidade e segurança

Biometria é dado pessoal **sensível** (LGPD, art. 5º, II, e art. 11). Isto não é parecer jurídico; é o que o código faz:

- **Nenhuma imagem é gravada**, nem no navegador nem no servidor: ela vive na memória durante a análise. Um teste procura colunas de imagem no banco.
- O **vetor** de cada amostra é cifrado com **AES-256-GCM** e amarrado à identidade dona dele: copiar um vetor para outra identidade o torna ilegível.
- A **chave** fica em `data/biometria.chave` (32 bytes, criada no primeiro cadastro, permissão restrita onde o sistema permite), separada do banco. Quem copia só o banco não lê os vetores. **Quem tem o computador inteiro (banco e chave) lê**; proteja a pasta `data/` e **nunca** envie `biometria.chave` ao GitHub (já está no `.gitignore`).
- Perdeu a chave? Os vetores ficam inúteis e as pessoas precisam ser recadastradas. Faça cópia da chave e do banco juntos, em lugar protegido.
- **Apagamento:** revogar o consentimento, remover o cadastro, excluir a identidade ou vencer a retenção apagam os vetores. A auditoria não guarda apelidos.
- A câmera só liga quando o administrador pede, e desliga ao sair da página, trocar de aba ou encerrar a sessão. O cabeçalho `Permissions-Policy` limita a câmera a esta página.
- O reconhecimento só pode ser acionado por **administrador logado**, porque quem envia a imagem escolhe o que a câmera "vê".

## Entrar no aplicativo com o rosto (incremento 0.7)

Cada conta pode **cadastrar o próprio rosto** e depois entrar pela tela de login, sem digitar usuário nem senha. A senha continua funcionando sempre.

**Cadastro (Conta > Entrar com o rosto).** Qualquer usuário logado cadastra o próprio rosto: informa a **senha atual**, marca a **concordância com o termo** (versão `2026-10-02`) e a câmera tira 5 fotos guiadas. Valem as mesmas regras da porta (um rosto, nítido, grande, fotos da mesma pessoa), e o mesmo rosto **não** pode estar em duas contas. Os vetores ficam em `account_faces`, cifrados com escopo `conta`, então um vetor de conta não abre como vetor de identidade da porta e vice-versa. Refazer substitui; **Remover meu rosto** apaga os vetores. Um administrador pode remover o rosto de qualquer conta (Conta > Pessoas com acesso).

**Entrada (tela de login > Entrar com o rosto).**

1. A câmera tira uma foto **de frente**.
2. O servidor sorteia um **desafio**: virar o rosto bem pouco para a *esquerda* ou para a *direita*. A câmera tira 6 fotos durante o giro.
3. O servidor confere: a foto de frente tem giro pequeno (< 0,15); alguma foto virada passa de 0,22 **no lado sorteado**; o rosto de frente corresponde a **uma única conta** (similaridade ≥ 0,55 e margem de 0,08 sobre a segunda); e o rosto virado é da mesma pessoa (até 0,10 abaixo do limite, porque de lado o rosto se parece menos).
4. Só então a sessão começa (mesmo cookie e mesmas regras do login por senha). Conta desativada, sem e-mail confirmado ou pendente nunca entra.

O desafio vale **uma vez** e expira em 45 segundos. O cancelamento na interface solicita sua remoção pelo token secreto. A expiração e o cancelamento são verificados após a leitura; a galeria atual e a criação de sessão compartilham a trava das alterações de conta e rosto. Todas as leituras aproveitadas precisam corresponder ao rosto inicial. Se a gravação da sessão ultrapassar o prazo, ela é removida e nenhum cookie é entregue. 5 recusas em 120 segundos (ou 20 tentativas por minuto) bloqueiam novas tentativas para todos por um tempo, e o rosto certo também espera. Problemas de captura (sem rosto, borrado) não contam como recusa.

**Mensagens.** Rosto fora do banco: *"Face não cadastrada. Este rosto não está no banco de dados do EverLock..."* (`no_match`). Nenhuma conta com rosto: `no_faces_enrolled`. Sem o giro pedido: `liveness_failed`. O reconhecimento da porta usa a mesma redação: *"Face não cadastrada. Este rosto não está no banco de identidades"*.

**O que isto NÃO garante.** O desafio de giro é um filtro contra foto parada, não uma prova de vida robusta. Um vídeo gravado da pessoa, ou uma foto segurada e girada diante da câmera, podem passar. Por isso a entrada por rosto é **uma conveniência de laboratório**. Ela vale para todas as contas, inclusive administradores, mas **uma sessão aberta pelo rosto não cria convites nem administradores e não promove contas a administrador**: essas ações pedem uma sessão aberta com senha (`password_required`). Assim, uma foto que engane a câmera não consegue entregar o controle do laboratório. O uso normal (porta, comandos, ver contas e histórico, criar usuários comuns) continua sem atrito. Os limites de giro (0,15 e 0,22) e o sentido do giro (esquerda da pessoa = nariz para a direita da imagem) vêm do desenho do detector e **não foram medidos com uma câmera real**; `scripts/testar_rosto.py` mostra o giro de cada foto para conferir. Se um lado for sempre recusado, o sentido está invertido na sua câmera e o ajuste é um sinal em `face_login.py`.

## Limitações

- **Desafio de movimento simples, não prova de vida forte.** Tanto a porta virtual quanto a entrada no aplicativo pedem um giro curto. Isso barra uma foto parada, mas um vídeo gravado ou uma foto movimentada à frente da câmera ainda podem passar. Prova de vida forte exige técnica e equipamento próprios, como profundidade ou infravermelho.
- **Limites não validados.** Não há medição de precisão com pessoas reais do grupo.
- **Validação real limitada.** Na retomada de 03/10/2026, OpenCV 4.13 carregou YuNet/SFace disponíveis localmente e recusou uma imagem vazia com `no_face`. Isso confirma carga dos modelos e execução do detector; não mede reconhecimento de pessoas. A lógica de cadastro, comparação, bloqueio, cifra e apagamento tem testes com motor falso. Use o [protocolo de avaliação](avaliacao-facial.md) com imagens autorizadas para medir erros e latência.
- Luz fraca, óculos escuros, máscara e ângulos extremos pioram o resultado. Gêmeos e parentes próximos podem ser confundidos.
- Uma câmera por computador e um administrador logado: ainda não há modo "quiosque" para a pessoa se identificar sozinha na porta.
- O consentimento ainda é registrado pelo administrador, não pela própria pessoa.

## Próximos passos sugeridos

1. Executar a etapa 12 com o [protocolo de avaliação](avaliacao-facial.md), sem reutilizar fotos de cadastro nos testes; só propor ajustes depois dos números.
2. Concluir o aceite de consentimento registrado pela própria pessoa (etapa 10).
3. Reproduzir os [cenários integrados](cenarios-integrados.md) e o roteiro de apresentação com outra pessoa (etapas 13 e 14). Não adicionar modo quiosque ou transporte remoto neste incremento.
