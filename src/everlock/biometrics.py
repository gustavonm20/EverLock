"""Vetores faciais: empacotamento, comparação e cifra em repouso.

Um vetor facial (128 números) é um dado biométrico. Ele nunca é gravado em texto: cada vetor é
cifrado com AES-256-GCM e amarrado à identidade dona dele (dado associado), de modo que copiar
o conteúdo de uma identidade para outra falha na abertura. A chave fica em um arquivo separado
do banco; quem copia só o banco não consegue ler os vetores. Quem tem acesso ao computador
inteiro (banco e chave) consegue, e a documentação deixa isso explícito.
"""

import array
import math
import os
from pathlib import Path

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # biblioteca ausente: o cadastro facial fica indisponível
    AESGCM = None
    InvalidTag = ValueError

VECTOR_SIZE = 128  # tamanho do vetor do modelo SFace
KEY_BYTES = 32
NONCE_BYTES = 12


def pack(vector) -> bytes:
    values = array.array("f", vector)
    if len(values) != VECTOR_SIZE or not all(math.isfinite(value) for value in values):
        raise ValueError("Vetor facial inválido.")
    return values.tobytes()


def unpack(data: bytes) -> tuple[float, ...]:
    values = array.array("f")
    if len(data) != VECTOR_SIZE * values.itemsize:
        raise ValueError("Vetor facial corrompido.")
    values.frombytes(data)
    return tuple(values)


def cosine(first, second) -> float:
    """Similaridade de cosseno entre dois vetores, de -1 a 1."""
    dot = sum(a * b for a, b in zip(first, second, strict=True))
    norms = math.sqrt(sum(a * a for a in first)) * math.sqrt(sum(b * b for b in second))
    return dot / norms if norms else 0.0


class TemplateVault:
    def __init__(self, key_path: Path):
        self.key_path = Path(key_path)
        self._cipher = None

    @property
    def available(self) -> bool:
        return AESGCM is not None

    def _aead(self):
        if AESGCM is None:
            raise RuntimeError("A biblioteca 'cryptography' não está instalada.")
        if self._cipher is None:
            self._cipher = AESGCM(self._load_key())
        return self._cipher

    def _load_key(self) -> bytes:
        try:
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            # O_EXCL: dois processos nunca criam chaves diferentes ao mesmo tempo.
            fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(os.urandom(KEY_BYTES))
        except FileExistsError:
            pass
        key = self.key_path.read_bytes()
        if len(key) != KEY_BYTES:
            raise RuntimeError(f"Arquivo de chave inválido: {self.key_path.name}.")
        return key

    @staticmethod
    def _context(owner_id: int, scope: str) -> bytes:
        # O escopo ("identidade" da porta ou "conta" do aplicativo) impede que um vetor de um
        # lado seja aceito no outro, mesmo com o mesmo número.
        return f"everlock:{scope}:{owner_id}".encode()

    def seal(self, owner_id: int, vector, scope: str = "identidade") -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        return nonce + self._aead().encrypt(nonce, pack(vector), self._context(owner_id, scope))

    def open(self, owner_id: int, sealed: bytes, scope: str = "identidade") -> tuple[float, ...]:
        try:
            plain = self._aead().decrypt(
                sealed[:NONCE_BYTES], sealed[NONCE_BYTES:], self._context(owner_id, scope),
            )
        except InvalidTag as error:
            raise ValueError("Vetor ilegível: chave diferente ou dado adulterado.") from error
        return unpack(plain)
