# Avaliação do EverLock com o grupo

Roteiro para usar a versão 0.16 depois da atualização. Reserve o computador, a
câmera e as pessoas que autorizaram participar. Preencha os resultados ao executar;
as verificações automatizadas anteriores não encerram este ensaio.

## 1. Preparar a instalação e os dados

1. Se há cadastros existentes, faça uma cópia por `backup.cmd` na instalação atual.
   Guarde o arquivo e a senha. Atualize o projeto com o servidor fechado, preservando
   `data/` e `everlock.env`. A 0.16 não muda o esquema do banco.
2. Abra no VS Code a pasta com `iniciar.cmd` e `pyproject.toml`; execute
   `.\iniciar.cmd` no terminal e acesse `http://127.0.0.1:8000`.
3. Entre com sua conta existente. Em **Configuração**, consulte o diagnóstico.
   Disponibilidade do motor e da biblioteca de cifra não comprova reconhecimento.
   Se faltarem modelos, consulte [reconhecimento facial](facial-recognition.md).
4. Escolha um ambiente bem iluminado, sem luz forte atrás da pessoa. Feche programas
   que usam a câmera. Use somente uma pessoa no enquadramento.

## 2. Montar as fotos da avaliação offline

Obtenha a autorização de cada pessoa e registre localmente finalidade, prazo e
apagamento. Use códigos (`p001`, `p002`), não nomes no manifesto ou nas pastas.
O aceite deste conjunto é separado do cadastro de identidades dentro do aplicativo.

Crie `data/avaliacao/` e copie para ela o [manifesto de exemplo](examples/avaliacao-facial.manifest.example.json)
como `manifest.json`. A estrutura sugerida é:

```text
data/avaliacao/
  manifest.json
  cadastro/
    p001-1.jpg
    p001-2.jpg
    p001-3.jpg
  teste/
    p001-1.jpg
    p001-2.jpg
    p002-1.jpg
    p002-2.jpg
```

No exemplo, `p001` está na galeria e `p002` é uma pessoa autorizada fora da galeria.
Adapte à composição real do grupo. Cada pessoa cadastrada precisa de 3 a 5 fotos
de cadastro e fotos novas de teste, preferencialmente de outra sessão. Arquivos
com nomes iguais nas duas pastas precisam ser capturas diferentes. Não reutilize
recortes ou quadros vizinhos do mesmo vídeo como avaliação independente.

O cadastro pela interface não salva fotos para esse conjunto. Tire essas imagens
separadamente com câmera/celular e copie-as para a pasta local. Use JPEG/PNG até
1,5 MB e informe no manifesto somente caminhos relativos. Pessoas que participam
só como desconhecidas ficam com `enrollment: []`. Se todas estiverem na galeria,
registre que não foi possível medir falsas aceitações de desconhecidos.

Marque `consent: true` somente após o aceite correspondente. Não publique fotos,
manifestos preenchidos ou relatórios individuais; mantenha-os dentro de `data/`.

## 3. Conferir e executar

No terminal do VS Code, na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe scripts\avaliar_rostos.py data\avaliacao\manifest.json --check-only
.\.venv\Scripts\python.exe scripts\avaliar_rostos.py data\avaliacao\manifest.json --profile door --output data\avaliacao\porta-01.json
.\.venv\Scripts\python.exe scripts\avaliar_rostos.py data\avaliacao\manifest.json --profile login --output data\avaliacao\login-01.json
```

A primeira chamada confere os arquivos e declarações sem analisar rostos. Corrija
os problemas antes de executar as outras. `ready: true` não mede qualidade das fotos.
Se o conjunto mudar durante a avaliação, a execução é interrompida: confira-o e
tente novamente. Relatórios existentes são preservados; escolha outro nome.

Leia `counts`, `rates`, falhas de captura e cadastros recusados juntos. Uma taxa
`null` indica ausência de tentativas válidas para medi-la. Código de saída 0
significa que a avaliação foi executada com galeria, não que a precisão foi aprovada.
Registre computador, câmera, iluminação, número de pessoas e sessões. O relatório
inclui versão do aplicativo e data UTC. Veja a interpretação em [avaliação facial](avaliacao-facial.md).

## 4. Ensaiar pela câmera no aplicativo

1. Em **Identidades**, leia o termo com a pessoa, defina retenção/horário e crie a
   identidade. Criar a identidade ainda não cadastra o rosto.
2. Selecione **Cadastrar rosto (câmera)**. Entregue o controle à pessoa para ler e
   marcar o aceite. A sessão administrativa registra essa declaração; o sistema
   não comprova independentemente quem clicou.
3. Selecione **Concordo e ligar câmera**. Aguarde a prévia aparecer. Se cancelar ou
   sair da conta durante a permissão, uma resposta tardia não deve reabrir a câmera.
   A abertura pode encerrar após 15 segundos de espera pela permissão ou 10 sem imagem;
   confira as permissões e tente novamente.
4. Inicie a captura e siga as cinco instruções. O resultado precisa indicar sucesso;
   erro de qualidade exige repetir o cadastro. Cadastrar o rosto não libera a trava.
   Na 0.16.1, as cinco marcações e a contagem acompanham as fotos capturadas; chegar
   a cinco não significa que a análise aprovou o rosto. Aguarde a mensagem final.
5. Em **Visão geral → Reconhecimento facial**, ligue a câmera e reconheça seguindo o
   giro sorteado. A liberação deve durar três segundos virtuais e a porta continuar
   fechada até a ação de entrada. Verifique também o sentido do giro na câmera usada.
6. Teste uma pessoa autorizada fora da galeria, ausência de giro, revogação e uma
   identidade fora do horário. Anote qualquer aceitação ou recusa inesperada.
7. Confira que **Cancelar**, troca de página e logout encerram a câmera. Outra pessoa
   deve reproduzir o [roteiro de apresentação](roteiro-apresentacao.md).

O desafio simples pode ser enganado por vídeo ou foto movimentada. Registre as
limitações observadas; não ajuste os limites apenas para fazer uma tentativa passar.
Qualquer calibração precisa de avaliação separada para conferir a escolha.

## 5. Registrar o resultado para a próxima revisão

Preencha localmente:

- Versão, data, computador, câmera e condições de iluminação.
- Quantidade de pessoas na galeria, desconhecidos e tentativas válidas.
- Cadastros recusados e falhas de captura.
- Reconhecimentos corretos, recusas indevidas e aceitações/trocas indevidas.
- Giro, cancelamento, revogação e saída manual observados.
- Problemas encontrados e o passo exato que os reproduz.

Compartilhe um resumo agregado autorizado e a descrição dos problemas. Os arquivos
de fotos e os relatórios por pessoa ficam no conjunto local. Nobreak, SMTP real e
n8n têm roteiros próprios e continuam pendentes até seus respectivos ensaios.
