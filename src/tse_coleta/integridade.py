"""Cadeia de integridade dos arquivos de urna.

1. `hash` publicado no JSON auxiliar (hex de um texto base64 em que o TSE troca `/` por `-`)
   == SHA-256 do `vota.vsc` (pacote de assinaturas da urna).
2. O `vota.vsc` contém o SHA-512 do `bu.dat` (assinado pela urna).

Obs.: a etapa 2 confere a presença do SHA-512 do BU dentro do vsc. A verificação criptográfica
da assinatura em si (ASN.1 + certificados do TSE) fica para a fase de decodificação.
"""

from __future__ import annotations

import base64
import binascii
import hashlib

from .codigos import validar


class HashInvalido(ValueError):
    pass


def decodificar_hash_tse(hash_hex: str) -> bytes:
    """Converte o `hash` do aux no digest SHA-256 (32 bytes)."""
    validar("hash_hex", hash_hex)
    try:
        texto = binascii.unhexlify(hash_hex).decode("ascii")
        padrao = texto.replace("-", "/").replace("_", "+")
        digest = base64.b64decode(padrao, validate=True)
    except (binascii.Error, UnicodeDecodeError, ValueError) as e:
        raise HashInvalido(f"hash do TSE não decodificável: {hash_hex[:16]}…") from e
    if len(digest) != 32:
        raise HashInvalido(f"hash do TSE com {len(digest)} bytes (esperado 32)")
    return digest


def codificar_hash_tse(digest: bytes) -> str:
    """Inverso de `decodificar_hash_tse` (usado em testes e diagnósticos)."""
    texto = base64.b64encode(digest).decode("ascii").replace("/", "-")
    return binascii.hexlify(texto.encode("ascii")).decode("ascii")


def vsc_confere(vsc: bytes, hash_hex: str) -> bool:
    return hashlib.sha256(vsc).digest() == decodificar_hash_tse(hash_hex)


def arquivo_confere_com_vsc(conteudo: bytes, vsc: bytes) -> bool:
    """O SHA-512 do arquivo (bu/rdv/log) precisa estar dentro do vsc."""
    return len(conteudo) > 0 and hashlib.sha512(conteudo).digest() in vsc
