# Diagnóstico local

Entre como administrador e abra **Diagnóstico** no menu. A página reúne seis
verificações e mostra quando a consulta foi feita. **Atualizar diagnóstico** consulta
novamente o servidor; não há atualização automática contínua.

| Item | O que a consulta informa | Limite da verificação |
|---|---|---|
| Aplicação local | O servidor respondeu à sessão autenticada | Não mede disponibilidade futura nem o nobreak |
| Banco de dados | A conexão SQLite respondeu a uma leitura simples | Não verifica integridade, gravação ou restauração |
| Reconhecimento facial | O motor carregado está disponível ou falta uma dependência/modelo | Não abre a câmera, lê fotos ou mede precisão |
| Proteção dos cadastros | A biblioteca de cifra está disponível | Não abre/cria a chave nem verifica os vetores existentes |
| E-mail | A configuração está presente ou os links aparecem no terminal | Não testa credenciais nem envia mensagens |
| Notificações opcionais | Configuração presente, inválida, ausente ou último envio com falha | Não envia/reenvia eventos nem confirma processamento externo |

Os estados são **Disponível**, **Requer atenção** e **Informação**. Serviços opcionais
ausentes são informativos. Não existe um selo global de “tudo validado”: cada item
explica exatamente o que foi observado e o que ainda não foi conferido.

Ao mudar de página, sair da conta ou perder a sessão, os resultados são removidos.
Uma resposta atrasada não pode preencher a página de uma sessão anterior. Se a
consulta falhar, o usuário pode tentar novamente; o resultado antigo não é exibido
como atual. A página se adapta aos temas claro/escuro e à tela do celular.

## API

`GET /api/diagnostics` exige administrador: 401 para sessão ausente/expirada, 403
para usuário comum. A resposta usa `Cache-Control: no-store` e contém:

- `version`, `mode: "simulation"` e `checked_at` em UTC;
- `checks`: seis itens com `id`, `title`, `status`, `summary` e `detail`;
- `status` em `ok`, `attention` ou `info`.

Os identificadores são `application`, `database`, `face_engine`,
`biometric_storage`, `email` e `notifications`. O diagnóstico utiliza descrições
controladas, sem repassar mensagens brutas de exceções, caminhos locais, destinatários,
endereços de serviços, senhas, chaves ou dados de contas/identidades.

A consulta não altera a porta, relógio, energia ou configurações; não chama a
sincronização da simulação. O serviço de fundo continua operando normalmente. A
autorização mantém a auditoria existente de acessos recusados. Uma falha que impeça
o próprio servidor ou a autenticação de funcionar também pode impedir o diagnóstico.

Os [testes de interface](testes-interface.md) usam contas fictícias e ambiente
isolado. Os aceites humanos e externos permanecem em [pendencias.md](pendencias.md).
