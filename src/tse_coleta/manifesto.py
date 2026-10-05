"""Manifesto do snapshot: uma linha por seção, com o que se sabe dela naquele ciclo.

Também cuida do layout em disco e do diário do ciclo em andamento (retomada após queda).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import stat
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

STATUS_FINAL = "Totalizada"
_CAMPOS_TEMPO = {"verificado_em"}


@dataclass
class Registro:
    chave: str
    uf: str
    municipio: str
    zona: str
    secao: str
    tem_urna: bool
    agregada_a: str | None = None
    publicada: bool = False
    data_hora_lista: str | None = None   # da/ha da lista por UF
    status_tse: str | None = None        # do aux
    hashes: list[str] = field(default_factory=list)
    completa: bool = False               # todas as versões com BU+vsc validados no disco
    motivo: str | None = None            # erro/motivo se incompleta
    aux_rel: str | None = None
    verificado_em: str | None = None     # ISO; quando o aux foi consultado pela última vez

    @property
    def final(self) -> bool:
        if not self.tem_urna:
            return True
        return self.publicada and self.completa and self.status_tse == STATUS_FINAL

    def assinatura(self) -> tuple:
        """Conteúdo relevante para decidir se 'algo mudou' (ignora carimbos de tempo)."""
        return tuple(
            (f.name, tuple(v) if isinstance(v := getattr(self, f.name), list) else v)
            for f in fields(self)
            if f.name not in _CAMPOS_TEMPO
        )

    def para_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def de_json(cls, linha: str) -> "Registro":
        d = json.loads(linha)
        nomes = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in nomes})


class Layout:
    def __init__(self, raiz: Path | str):
        self.raiz = Path(raiz)
        self.espelho = self.raiz / "espelho"
        self.snapshots = self.raiz / "snapshots"
        self.estado = self.raiz / "estado"
        self.logs = self.raiz / "logs"
        self.diario = self.estado / "ciclo_em_andamento.jsonl"
        self.estado_atual = self.estado / "estado_atual.jsonl.gz"

    def criar(self) -> None:
        for p in (self.espelho, self.snapshots, self.estado, self.logs):
            p.mkdir(parents=True, exist_ok=True)


# ---------- manifesto ----------

def serializar_manifesto(registros: dict[str, Registro]) -> bytes:
    """jsonl.gz determinístico (ordenado, mtime=0) → mesmo conteúdo, mesmos bytes."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for chave in sorted(registros):
            gz.write(registros[chave].para_json().encode("utf-8") + b"\n")
    return buf.getvalue()


def ler_manifesto(caminho: Path) -> dict[str, Registro]:
    with gzip.open(caminho, "rt", encoding="utf-8") as f:
        regs = (Registro.de_json(l) for l in f if l.strip())
        return {r.chave: r for r in regs}


def ultimo_snapshot_com_manifesto(layout: Layout) -> Path | None:
    if not layout.snapshots.is_dir():
        return None
    candidatos = sorted(
        (p for p in layout.snapshots.iterdir() if (p / "manifesto.jsonl.gz").is_file()),
        key=lambda p: p.name,
    )
    return candidatos[-1] if candidatos else None


def gravar_estado_atual(layout: Layout, registros: dict[str, Registro]) -> None:
    """Estado de trabalho (inclui carimbos de verificação). Substituído atomicamente a cada ciclo.
    NÃO é histórico — o histórico imutável fica em snapshots/."""
    layout.estado.mkdir(parents=True, exist_ok=True)
    tmp = layout.estado_atual.with_name(layout.estado_atual.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(serializar_manifesto(registros))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, layout.estado_atual)


def carregar_estado(layout: Layout) -> tuple[dict[str, Registro] | None, dict[str, Registro] | None]:
    """Retorna (estado_de_trabalho, manifesto_do_ultimo_snapshot)."""
    snap = ultimo_snapshot_com_manifesto(layout)
    historico = ler_manifesto(snap / "manifesto.jsonl.gz") if snap else None
    trabalho = ler_manifesto(layout.estado_atual) if layout.estado_atual.is_file() else historico
    return trabalho, historico


def mudou(anterior: dict[str, Registro] | None, atual: dict[str, Registro]) -> bool:
    if anterior is None or anterior.keys() != atual.keys():
        return True
    return any(anterior[k].assinatura() != atual[k].assinatura() for k in atual)


# ---------- snapshot ----------

def gravar_snapshot(
    layout: Layout,
    nome: str,
    listas: dict[str, bytes],
    registros: dict[str, Registro],
    resumo: dict,
) -> Path:
    """Cria snapshots/<nome>/ com listas, manifesto, resumo e SHA256SUMS; deixa somente-leitura."""
    destino = layout.snapshots / nome
    destino.mkdir(parents=True, exist_ok=False)  # nunca reutiliza pasta existente
    arquivos: dict[str, bytes] = {f"listas/{uf}.json": b for uf, b in sorted(listas.items())}
    arquivos["manifesto.jsonl.gz"] = serializar_manifesto(registros)
    arquivos["resumo.json"] = json.dumps(resumo, ensure_ascii=False, indent=2, sort_keys=True).encode()
    linhas = []
    for rel, conteudo in arquivos.items():
        p = destino / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "xb") as f:
            f.write(conteudo)
            f.flush()
            os.fsync(f.fileno())
        linhas.append(f"{hashlib.sha256(conteudo).hexdigest()}  {rel}")
    (destino / "SHA256SUMS").write_text("\n".join(sorted(linhas, key=lambda l: l[66:])) + "\n")
    _somente_leitura(destino)
    return destino


def _somente_leitura(pasta: Path) -> None:
    ro = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    for p in sorted(pasta.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        p.chmod(ro | (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH if p.is_dir() else 0))
    pasta.chmod(ro | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ---------- diário do ciclo em andamento ----------

class Diario:
    """Append-only: cada seção coletada no ciclo atual vira uma linha. Permite retomar após queda."""

    def __init__(self, caminho: Path):
        self.caminho = caminho
        self._f = None

    def carregar(self) -> dict[str, Registro]:
        if not self.caminho.is_file():
            return {}
        regs: dict[str, Registro] = {}
        with open(self.caminho, encoding="utf-8") as f:
            for linha in f:
                try:
                    r = Registro.de_json(linha)
                except (json.JSONDecodeError, TypeError):
                    continue  # última linha truncada por queda
                regs[r.chave] = r
        return regs

    def anotar(self, r: Registro) -> None:
        if self._f is None:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            self._f = open(self.caminho, "a", encoding="utf-8")
        self._f.write(r.para_json() + "\n")
        self._f.flush()

    def fechar(self) -> None:
        """Fecha sem apagar (interrupção): o próximo ciclo retoma a partir dele."""
        if self._f is not None:
            self._f.close()
            self._f = None

    def encerrar(self) -> None:
        """Ciclo concluído e snapshot gravado: o diário não é mais necessário."""
        self.fechar()
        self.caminho.unlink(missing_ok=True)
