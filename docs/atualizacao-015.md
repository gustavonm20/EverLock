# Atualizar para 0.15

Esta entrega mantém Python/FastAPI, SQLite e HTML/CSS/JavaScript. Não troca o banco
por um serviço externo e não acrescenta dependências de execução.

## Preparar a atualização

1. Na versão anterior, faça uma cópia com `backup.cmd` e guarde a senha e o arquivo
   em lugar protegido. Não publique a pasta `data` nem o arquivo `everlock.env`.
2. Feche o EverLock, atualize os arquivos do projeto e preserve seus dados locais.
3. Execute `iniciar.cmd`. Na primeira inicialização, as migrações centralizadas
   adicionam índices e campos; contas, históricos e cadastros existentes permanecem.
4. Entre com a conta existente. Confira **Configuração**, **Identidades** e
   **Atividade**. O diagnóstico indica disponibilidade, não validação real.

O banco passa a registrar sua versão em `PRAGMA user_version`. A migração inteira
é transacional: uma falha desfaz o incremento; banco de versão futura é recusado.
Não abra o banco migrado em versões antigas. Para voltar, feche o aplicativo e
restaure a cópia anterior em uma instalação compatível; isso descarta alterações
posteriores à cópia. Consulte [backup](backup.md).

## Mudanças que precisam ser conhecidas

- **Histórico:** a API retorna `{items, next_cursor, has_more}`. Envie o último
  `next_cursor` em `before_id` para continuar. Novos eventos não deslocam registros
  já carregados. A tela oferece atualização manual e “Carregar mais”. O CSV informa
  quando há outra parte; não promete exportação ilimitada ou uma fotografia atômica
  de várias requisições.
- **Consentimento:** novos cadastros/regravações faciais de identidades exigem uma
  declaração explícita antes de ligar a câmera e enviar as fotos. O registro usa a
  sessão administrativa: é uma declaração, não prova independente de quem clicou.
  Não libera a trava nem prolonga a retenção. Vetores anteriores são preservados;
  a atualização não os revoga automaticamente nem presume um novo aceite pessoal.
- **Avisos:** a fila opcional passa a persistir somente metadados técnicos durante
  até 24 horas em `data/notificacoes.sqlite3`. Nomes e detalhes livres não são enviados.
  Falha de disco pode perder um aviso; entrega externa e deduplicação ainda precisam
  ser verificadas. Consulte [notificações](notifications.md).
- **Registros técnicos:** ao iniciar pela CLI/`iniciar.cmd`, `data/logs/requests.log`
  registra identificador da requisição, rota-modelo, status e duração, sem corpo,
  query, IP, senha ou token. Rotação em aproximadamente 1 MB, com três arquivos de
  reserva. Esses arquivos não são o histórico de auditoria do produto.
- **Limite de entrada:** corpos HTTP maiores que 16 MiB são recusados antes do
  parser, inclusive sem `Content-Length`. As restrições menores de cada campo e de
  cada imagem continuam em vigor. Isso não equivale a proteção completa contra
  sobrecarga; o servidor continua local e de instância única.
- **Menu:** Operação, Administração e Laboratório separam uso e demonstração;
  celular tem menu recolhível. Configuração reúne diagnóstico e guia de preparação,
  sem editar segredos pelo navegador. O roteiro de demonstração não executa ações
  automaticamente.

Os sete grupos de [aceites adiados](pendencias.md) permanecem pendentes. As
[skills](skills.md) ajudam no desenvolvimento, não controlam a porta.
