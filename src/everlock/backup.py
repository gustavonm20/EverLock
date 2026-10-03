"""Cópia de segurança e restauração dos dados do EverLock: banco e chave dos rostos.

O banco e a chave `biometria.chave` precisam andar juntos: sem a chave, os vetores faciais viram
lixo e as pessoas têm de se recadastrar. Por isso a cópia leva os dois. Como isso concentra tudo
o que é sensível num arquivo só, a cópia pode ser protegida por senha (AES-256-GCM, chave
derivada com scrypt). Sem senha, guarde o arquivo em lugar protegido.
"""

import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from everlock import __version__
from everlock.biometrics import AESGCM, InvalidTag

DB_NAME, KEY_NAME, MANIFEST = "everlock.sqlite3", "biometria.chave", "manifest.json"
MAGIC = b"ELBK1\n"
SALT_BYTES, NONCE_BYTES = 16, 12
MIN_PASSPHRASE = 8
MAX_UNPACKED = 500 * 1024 * 1024
SQLITE_HEADER = b"SQLite format 3\x00"


class BackupError(Exception):
    """Problema que o usuário pode corrigir; a mensagem diz como."""


def _derive(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(passphrase.encode(), salt=salt, n=2**15, r=8, p=1,
                          maxmem=64 * 1024 * 1024, dklen=32)


def _snapshot(source: Path, target: Path) -> None:
    """Cópia consistente do banco, mesmo com o servidor aberto (API de backup do SQLite)."""
    origin = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=10)
    try:
        copy = sqlite3.connect(target)
        try:
            origin.backup(copy)
        finally:
            copy.close()
    finally:
        origin.close()


def create_backup(data_dir: Path, out_dir: Path, passphrase: str | None = None,
                  now: datetime | None = None) -> Path:
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    database = data_dir / DB_NAME
    if not database.is_file():
        raise BackupError(f"Banco não encontrado em {data_dir}. Confira EVERLOCK_DATA_DIR.")
    if passphrase is not None and len(passphrase) < MIN_PASSPHRASE:
        raise BackupError(f"Use uma senha de pelo menos {MIN_PASSPHRASE} caracteres.")
    if passphrase is not None and AESGCM is None:
        raise BackupError("A biblioteca 'cryptography' não está instalada; rode .\\iniciar.cmd.")
    now = now or datetime.now()
    with tempfile.TemporaryDirectory() as temp:
        copy = Path(temp) / DB_NAME
        _snapshot(database, copy)
        members = {DB_NAME: copy.read_bytes()}
    key = data_dir / KEY_NAME
    if key.is_file():
        members[KEY_NAME] = key.read_bytes()
    manifest = {"app": "EverLock", "version": __version__, "created_at": now.isoformat(),
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in members.items()}}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, json.dumps(manifest, indent=2))
        for name, data in members.items():
            archive.writestr(name, data)
    payload = buffer.getvalue()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    if passphrase is None:
        path, content = out_dir / f"everlock-{stamp}.zip", payload
    else:
        salt, nonce = os.urandom(SALT_BYTES), os.urandom(NONCE_BYTES)
        sealed = AESGCM(_derive(passphrase, salt)).encrypt(nonce, payload, MAGIC)
        path, content = out_dir / f"everlock-{stamp}.elbak", MAGIC + salt + nonce + sealed
    out_dir.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
    return path


def _open_archive(raw: bytes, passphrase: str | None) -> zipfile.ZipFile:
    if raw.startswith(MAGIC):
        if not passphrase:
            raise BackupError("Esta cópia é protegida por senha. Informe a senha.")
        if AESGCM is None:
            raise BackupError("A biblioteca 'cryptography' não está instalada.")
        salt_end = len(MAGIC) + SALT_BYTES
        nonce_end = salt_end + NONCE_BYTES
        salt, nonce = raw[len(MAGIC):salt_end], raw[salt_end:nonce_end]
        try:
            raw = AESGCM(_derive(passphrase, salt)).decrypt(nonce, raw[nonce_end:], MAGIC)
        except InvalidTag as error:
            raise BackupError("Senha incorreta ou arquivo adulterado.") from error
    try:
        return zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as error:
        raise BackupError("O arquivo não é uma cópia de segurança do EverLock.") from error


def restore_backup(archive_path: Path, data_dir: Path, passphrase: str | None = None,
                   force: bool = False, now: datetime | None = None) -> list[str]:
    """Restaura a cópia. Pare o EverLock antes. Dados atuais vão para uma pasta de reserva."""
    archive_path, data_dir = Path(archive_path), Path(data_dir)
    if not archive_path.is_file():
        raise BackupError(f"Arquivo não encontrado: {archive_path}")
    archive = _open_archive(archive_path.read_bytes(), passphrase)
    allowed = {DB_NAME, KEY_NAME, MANIFEST}
    infos = archive.infolist()
    if (not infos or {info.filename for info in infos} - allowed
            or sum(info.file_size for info in infos) > MAX_UNPACKED):
        raise BackupError("O conteúdo da cópia não é o esperado; nada foi restaurado.")
    try:
        manifest = json.loads(archive.read(MANIFEST))
        contents = {name: archive.read(name) for name in manifest["files"]}
        valid = (set(contents) <= {DB_NAME, KEY_NAME} and DB_NAME in contents and all(
            hashlib.sha256(data).hexdigest() == manifest["files"][name]
            for name, data in contents.items()))
    except (KeyError, ValueError, TypeError):
        valid = False
    if not valid or not contents[DB_NAME].startswith(SQLITE_HEADER):
        raise BackupError("A cópia está incompleta ou corrompida; nada foi restaurado.")
    present = [name for name in (DB_NAME, KEY_NAME) if (data_dir / name).exists()]
    if present and not force:
        raise BackupError("Já existem dados neste computador. Use --forcar para substituí-los "
                          "(os atuais são guardados numa pasta de reserva).")
    data_dir.mkdir(parents=True, exist_ok=True)
    if present:
        reserve = data_dir / f"antes-da-restauracao-{(now or datetime.now()):%Y%m%d-%H%M%S}"
        reserve.mkdir()
        for name in present + [f"{DB_NAME}-wal", f"{DB_NAME}-shm"]:
            if (data_dir / name).exists():
                shutil.move(str(data_dir / name), reserve / name)
    for name, data in contents.items():
        descriptor = os.open(data_dir / name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
    return sorted(contents)
