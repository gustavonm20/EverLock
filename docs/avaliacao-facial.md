# Avaliação facial local

A etapa 12 agora tem uma ferramenta reproduzível: `scripts/avaliar_rostos.py`. Ela usa o
mesmo motor YuNet/SFace, a validação de cadastro e a comparação de identidades do EverLock.
Cada foto de teste é comparada com todas as pessoas cadastradas (identificação 1:N), usando a
melhor amostra de cada pessoa e a regra atual de ambiguidade. Não abre a porta, não cria
cadastros no banco e não altera limites do aplicativo.

A ferramenta está validada com resultados sintéticos. **A precisão real e a calibração
continuam pendentes** até o grupo fornecer e executar um conjunto autorizado de imagens.

## Preparar um conjunto autorizado

1. Obtenha autorização explícita de cada participante para esta avaliação, incluindo quem
   aparecerá somente como desconhecido. Defina finalidade, acesso, prazo e apagamento das
   imagens e do relatório. Registre essa autorização localmente; `consent: true` é uma
   declaração de quem preparou o manifesto, não substitui o consentimento da pessoa nem
   o fluxo de consentimento do aplicativo.
2. Crie `data/avaliacao/` e copie para lá o
   [modelo do manifesto](examples/avaliacao-facial.manifest.example.json), renomeando-o para
   `manifest.json`. O modelo não inclui fotos nem pessoas reais e começa com consentimento
   falso. Troque para `true` somente após a autorização correspondente.
3. Use códigos como `p001`, sem nomes reais. Para cada pessoa cadastrada, separe de 3 a 5
   fotos em `cadastro/` e fotos **novas** em `teste/`. Prefira outra sessão de captura;
   não reutilize a foto de cadastro, seus recortes ou quadros vizinhos do mesmo vídeo.
4. Inclua pessoas autorizadas que não estejam na galeria, com `enrollment: []`. Essas
   pessoas permitem medir falsas aceitações. Inclua também fotos de teste das pessoas
   cadastradas, para medir rejeições e trocas de identidade.
5. Use JPEG ou PNG de até 1,5 MB, com caminhos relativos e dentro da pasta do manifesto.
   O motor exige um rosto, qualidade e tamanho mínimos. Varie as condições de teste de
   forma documentada: iluminação, distância e acessórios, sem misturar pessoas numa foto.

O arquivo não aceita uma imagem repetida nem uma cópia com outro nome: verifica o caminho e
o conteúdo. Recortes ou versões modificadas da mesma captura ainda precisam de revisão
humana. Todos os consentimentos e a separação de arquivos são verificados antes de ler
rostos. Arquivos ausentes, grandes demais, sem rosto, com vários rostos ou borrados aparecem
como falhas de captura. A pasta `data/` já é ignorada pelo Git; mantenha nela o conjunto e o
relatório. Não envie fotos, manifesto pessoal ou relatório individual ao GitHub/Notion.

## Executar

Prepare os modelos pelo iniciador normal (`iniciar.cmd`) ou pelo roteiro de
[reconhecimento facial](facial-recognition.md). A avaliação não baixa modelos nem precisa de
internet depois dessa preparação.

Na pasta do projeto:

```powershell
.\.venv\Scripts\python scripts\avaliar_rostos.py data\avaliacao\manifest.json --profile door --output data\avaliacao\porta-01.json
.\.venv\Scripts\python scripts\avaliar_rostos.py data\avaliacao\manifest.json --profile login --output data\avaliacao\login-01.json
```

`door` usa os limites atuais da porta (similaridade 0,45 e margem 0,05); `login` usa os do
login (0,55 e 0,08). `--models-dir` escolhe outra pasta de modelos. Sem `--output`, o JSON é
mostrado no terminal. Um relatório existente não é sobrescrito; escolha um nome novo.
Código de saída 0 indica uma avaliação com galeria válida, 2 indica todos os cadastros
recusados, e 1 indica erro de manifesto, motor ou gravação. Código 0 não significa que o
reconhecimento atingiu uma meta de precisão.

Para comparar um limite experimental, use `--threshold 0.50 --margin 0.05` e outro nome de
relatório. Esses parâmetros afetam somente essa execução. Ajustar limites exige analisar
os resultados e validar a escolha em outro conjunto reservado; escolher e declarar
precisão no mesmo conjunto favorece resultados otimistas. A ferramenta não busca
automaticamente um limite nem altera `FaceSettings`/`LoginSettings`.

## Ler as taxas

Os valores são frações de 0 a 1 (0,10 = 10%). Cada imagem válida de teste conta uma vez,
mesmo com várias pessoas e amostras cadastradas. Os numeradores e denominadores estão em
`counts`; o tamanho efetivo da galeria está em `gallery`.

| Campo em `rates` | Cálculo |
|---|---|
| `false_acceptance_rate` | Desconhecidos aceitos como alguma pessoa / tentativas válidas de desconhecidos |
| `false_rejection_rate` | Pessoas cadastradas recusadas (`no_match` ou `ambiguous`) / tentativas válidas de cadastrados |
| `false_identification_rate` | Pessoas cadastradas aceitas como outra pessoa / tentativas válidas de cadastrados |
| `genuine_failure_rate` | Rejeições + trocas de identidade / tentativas válidas de cadastrados |
| `correct_identification_rate` | Cadastrados reconhecidos corretamente / tentativas válidas de cadastrados |

Uma troca de identidade é registrada separadamente de uma rejeição: somá-las em
`genuine_failure_rate` evita esconder um resultado incorreto como sucesso. Falsa aceitação
aqui é uma decisão **1:N de um desconhecido**, não a proporção de pares diferentes que
passam de um limite. Se faltar o denominador, a taxa é `null`, nunca zero.

`captures` registra códigos de falha e, quando possível, tamanho, nitidez, detecção e giro.
Falhas de captura não entram nos denominadores acima; analise também
`genuine_capture_failures` e `unknown_capture_failures`, porque descartá-las pode esconder
problemas de uso. Se um cadastro não passa pela validação (amostras insuficientes,
inconsistentes ou rosto já cadastrado), seus testes ficam `enrollment_failed` e entram em
`skipped_tests`; não são tratados como desconhecidos. Sem galeria, todos ficam `no_gallery`.
Os cadastros são processados na ordem do manifesto, como cadastros sucessivos no aplicativo.

`engine_ms` mede a leitura de cada captura pelo motor. `latency_ms` mede cada cadastro ou
tentativa de identificação; `latency.identification` resume somente tentativas válidas em
milissegundos, com quantidade, média, mínimo, máximo e p95 pelo método de posto mais próximo.
Sem tentativas válidas, essas medidas são `null`. O relógio é monotônico. A leitura dos arquivos,
carregamento dos modelos, câmera, rede, giro e autorização ficam fora dessa latência; não a
apresente como tempo total para entrar na aplicação ou liberar a porta. O primeiro uso pode
aquecer o motor, por isso registre a máquina, ordem e condições de execução junto do conjunto.

O relatório guarda somente códigos anônimos, medidas, decisões, contagens e limites.
Não guarda imagens, vetores, nomes de arquivo, caminhos ou hashes. Os vetores existem na
memória durante a execução e não são inseridos no banco. Códigos e resultados ainda podem
identificar participantes para quem conhece a correspondência; proteja o relatório local.

## Limites da medição

Esta execução mede identificação antes do desafio de movimento e da autorização. Não
valida prova de vida, sentido de giro na câmera, sessões, consentimento/horário em tempo de
acesso, falhas de conexão ou liberação da trava. As medidas de `yaw` ajudam a inspecionar os
limites provisórios de giro (0,15 e 0,22), mas fotos isoladas não demonstram um desafio real.
Esses cenários precisam da demonstração integrada da etapa 13.

Poucas pessoas, condições semelhantes e testes repetidos da mesma pessoa não representam
a população nem fornecem tentativas independentes. Zero erros nesse conjunto não garante
segurança. Registre localmente quantidade de pessoas, tentativas, sessões e condições; ao
atualizar os quadros, publique somente o resumo agregado autorizado e as limitações. A
etapa 12 só pode ser concluída após a execução real, revisão dos erros e documentação das
condições e limitações.
