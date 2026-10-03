# Cópia de segurança e restauração

Os dados do EverLock ficam na pasta `data/`: o banco (`everlock.sqlite3`) e, se alguém cadastrou rosto, a chave `biometria.chave`. **Sem a chave, os vetores faciais viram lixo** e todos precisam se recadastrar. Por isso a cópia leva os dois juntos.

## Criar

Dê dois cliques em `backup.cmd` (ou, no terminal, `.\.venv\Scripts\python -m everlock backup --senha`). Ele pede uma senha, que **você precisa guardar**: sem ela a cópia não abre. O arquivo vai para a pasta `backups/` (ignorada pelo Git) como `everlock-AAAAMMDD-HHMMSS.elbak`.

- Pode ser feita com o app aberto: a cópia do banco é consistente.
- Sem `--senha` sai um `.zip` comum, e o programa avisa que ele contém banco e chave sem proteção.
- Com senha, o conteúdo é cifrado com AES-256-GCM (chave derivada da senha com scrypt); senha errada ou arquivo alterado são recusados.
- Use `--pasta D:\caminho` para escolher onde salvar. **Guarde uma cópia fora deste computador** (pendrive ou nuvem privada), pois uma cópia na mesma máquina não protege contra a perda do disco.

## Restaurar

1. **Feche o EverLock.**
2. `.\.venv\Scripts\python -m everlock restaurar backups\everlock-AAAAMMDD-HHMMSS.elbak --senha`
3. Se já existirem dados, o comando recusa. Com `--forcar`, ele substitui, e os dados atuais vão para `data/antes-da-restauracao-AAAAMMDD-HHMMSS/`.
4. A restauração confere um manifesto com o SHA-256 de cada arquivo, aceita só os nomes esperados (nada de caminhos como `..\`) e exige que o banco seja um SQLite válido.

## Limites

- Não há cópia automática agendada: é preciso rodar o comando.
- Quem tem o arquivo `.zip` sem senha tem banco e chave. Prefira sempre `--senha`.
- Restaurar uma cópia antiga **desfaz** contas, cadastros e histórico criados depois dela.
