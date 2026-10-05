"""Espelho em disco: gravação atômica e imutável.

Regras:
- Nada é gravado fora da raiz (defesa extra além da validação de códigos).
- Escreve em `<nome>.part`, faz fsync e só então renomeia para o nome final.
- Nunca sobrescreve: se o arquivo final já existe com conteúdo diferente, levanta erro e
  preserva o original.
- Arquivos que mudam no mesmo endereço do TSE (aux, listas, agregados) são gravados
  versionados: `<stem>@<sha256[:16]><ext>`, deduplicando por conteúdo.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path, PurePosixPath


class ConflitoDeConteudo(RuntimeError):
    """Já existe arquivo com o mesmo nome e conteúdo diferente — original preservado."""


class CaminhoForaDaRaiz(ValueError):
    pass


class Espelho:
    def __init__(self, raiz: Path | str):
        self.raiz = Path(raiz).resolve()

    def caminho(self, rel: str) -> Path:
        p = PurePosixPath(rel)
        if p.is_absolute() or ".." in p.parts or not p.parts:
            raise CaminhoForaDaRaiz(rel)
        destino = (self.raiz / Path(*p.parts)).resolve()
        if self.raiz not in destino.parents:
            raise CaminhoForaDaRaiz(rel)
        return destino

    def ler(self, rel: str) -> bytes | None:
        p = self.caminho(rel)
        return p.read_bytes() if p.is_file() else None

    def gravar_imutavel(self, rel: str, conteudo: bytes) -> bool:
        """Grava se não existir. Retorna True se gravou, False se já existia idêntico."""
        destino = self.caminho(rel)
        if not destino.exists():
            try:
                _gravar_atomico(destino, conteudo)
                return True
            except FileExistsError:
                pass  # outro gravou no meio-tempo; compara abaixo
        if destino.read_bytes() == conteudo:
            return False
        raise ConflitoDeConteudo(rel)

    def gravar_versionado(self, rel: str, conteudo: bytes) -> tuple[str, bool]:
        """Grava `<stem>@<sha256[:16]><ext>`. Retorna (caminho relativo, gravou?)."""
        p = PurePosixPath(rel)
        tag = hashlib.sha256(conteudo).hexdigest()[:16]
        rel_v = str(p.with_name(f"{p.stem}@{tag}{p.suffix}"))
        return rel_v, self.gravar_imutavel(rel_v, conteudo)


def _gravar_atomico(destino: Path, conteudo: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(f"{destino.name}.{os.getpid()}.{secrets.token_hex(4)}.part")
    try:
        with open(tmp, "wb") as f:
            f.write(conteudo)
            f.flush()
            os.fsync(f.fileno())
        # link() falha se o destino já existir → nunca sobrescreve, mesmo em corrida
        os.link(tmp, destino)
    finally:
        tmp.unlink(missing_ok=True)
