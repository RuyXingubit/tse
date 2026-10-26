"""Decodificador ASN.1 BER em Python puro para arquivos `bu.dat` (Boletim de Urna) do TSE.

Extrai:
- Identificação da seção (`municipio`, `zona`, `local`, `secao`), `pleito` e `fase`.
- Identificação da urna física (`numero_interno_urna`, `versao_votacao`).
- Horários (`abertura`, `encerramento`, `emissao`).
- Comparecimento geral e detalhamento biométrico (`habilitados_biometria`, `liberados_codigo`,
  `habilitados_outros`).
- Resultados por eleição e cargo (`aptos`, `comparecimento`, votos nominais por candidato,
  `brancos`, `nulos`, `legenda`, `total`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

TagASN1 = tuple[int, int]  # (classe, numero_tag)
NoASN1 = tuple[TagASN1, bytes | list["NoASN1"]]


class ErroDecodificacaoBU(ValueError):
    """Arquivo `bu.dat` truncado, malformado ou fora da estrutura ASN.1 esperada."""


@dataclass(frozen=True, slots=True)
class VotacaoCargo:
    eleicao: int
    cargo: int
    aptos: int
    comparecimento: int
    nominais: dict[int, int] = field(default_factory=dict)
    brancos: int = 0
    nulos: int = 0
    legenda: int = 0
    anulados_apuracao: int = 0
    total: int = 0


@dataclass(frozen=True, slots=True)
class BoletimUrnaDecodificado:
    pleito: int
    fase: int
    municipio: int
    zona: int
    local: int
    secao: int
    numero_interno_urna: int
    versao_votacao: str
    abertura: str
    encerramento: str
    emissao: str
    comparecimento_urna: int
    habilitados_biometria: int
    liberados_codigo: int
    habilitados_outros: int
    cargos: dict[int, VotacaoCargo]  # cargo (ex.: 1=Presidente, 3=Governador) -> VotacaoCargo


def decodificar_ber(dados: bytes, inicio: int = 0, fim: int | None = None) -> list[NoASN1]:
    """Decodifica uma sequência de elementos TLV ASN.1 BER."""
    if fim is None:
        fim = len(dados)
    if inicio < 0 or fim > len(dados) or inicio > fim:
        raise ErroDecodificacaoBU("limites ASN.1 inválidos")
    itens: list[NoASN1] = []
    pos = inicio
    while pos < fim:
        b0 = dados[pos]
        pos += 1
        classe = (b0 >> 6) & 0x03
        construido = bool(b0 & 0x20)
        tag = b0 & 0x1F
        if tag == 0x1F:
            tag = 0
            lidos = 0
            while True:
                if pos >= fim or lidos > 4:
                    raise ErroDecodificacaoBU("tag ASN.1 truncada ou longa demais")
                b = dados[pos]
                pos += 1
                lidos += 1
                tag = (tag << 7) | (b & 0x7F)
                if not (b & 0x80):
                    break
        if pos >= fim:
            raise ErroDecodificacaoBU("comprimento ASN.1 truncado")
        lb = dados[pos]
        pos += 1
        if lb == 0x80:
            raise ErroDecodificacaoBU("comprimento indefinido BER não suportado")
        if lb & 0x80:
            n_bytes = lb & 0x7F
            if n_bytes == 0 or n_bytes > 4 or pos + n_bytes > fim:
                raise ErroDecodificacaoBU("comprimento longo ASN.1 inválido")
            tamanho = int.from_bytes(dados[pos : pos + n_bytes], "big")
            pos += n_bytes
        else:
            tamanho = lb
        if pos + tamanho > fim:
            raise ErroDecodificacaoBU("valor ASN.1 ultrapassa o fim do buffer")
        fatia = dados[pos : pos + tamanho]
        pos += tamanho
        if construido:
            itens.append(((classe, tag), decodificar_ber(fatia)))
        else:
            itens.append(((classe, tag), fatia))
    return itens


def _int(val: bytes | list[NoASN1]) -> int:
    if not isinstance(val, bytes) or len(val) == 0:
        raise ErroDecodificacaoBU("esperado inteiro ASN.1")
    return int.from_bytes(val, "big", signed=False)


def _str(val: bytes | list[NoASN1]) -> str:
    if not isinstance(val, bytes):
        raise ErroDecodificacaoBU("esperado texto ASN.1")
    return val.decode("latin-1", errors="replace").strip()


def _lista(val: bytes | list[NoASN1]) -> list[NoASN1]:
    if not isinstance(val, list):
        raise ErroDecodificacaoBU("esperada sequência construída ASN.1")
    return val


def decodificar_bu(dados: bytes) -> BoletimUrnaDecodificado:
    """Decodifica os bytes de um arquivo `-bu.dat` oficial do TSE."""
    if not dados:
        raise ErroDecodificacaoBU("bu.dat vazio")
    raiz = decodificar_ber(dados)
    if not raiz or raiz[0][0] != (0, 16):
        raise ErroDecodificacaoBU("envelope raiz ASN.1 ausente")
    env = _lista(raiz[0][1])
    octeto_bu: bytes | None = None
    for tag, val in env:
        if tag == (0, 4) and isinstance(val, bytes):
            octeto_bu = val
            break
    if not octeto_bu:
        raise ErroDecodificacaoBU("conteúdo interno do BU ausente no envelope")

    arvore_bu = decodificar_ber(octeto_bu)
    if not arvore_bu or arvore_bu[0][0] != (0, 16):
        raise ErroDecodificacaoBU("EntidadeBoletimUrna inválida")
    itens = _lista(arvore_bu[0][1])
    if len(itens) < 6:
        raise ErroDecodificacaoBU("EntidadeBoletimUrna incompleta")

    # 0: CabecalhoEntidade
    cab = _lista(itens[0][1])
    pleito = 0
    for tag, val in cab:
        if tag[0] == 2 and isinstance(val, bytes):
            pleito = _int(val)

    # 1: Fase
    fase = _int(itens[1][1])

    # 2: Urna
    urna_seq = _lista(itens[2][1])
    versao_votacao = ""
    numero_interno_urna = 0
    for tag, val in urna_seq:
        if tag == (0, 27) and isinstance(val, bytes) and not versao_votacao:
            versao_votacao = _str(val)
        elif tag == (0, 16) and isinstance(val, list):
            for t2, v2 in val:
                if t2 == (0, 16) and isinstance(v2, list):
                    for t3, v3 in v2:
                        if t3 == (0, 2) and isinstance(v3, bytes) and numero_interno_urna == 0:
                            numero_interno_urna = _int(v3)
                            break

    # 3: IdentificacaoSecaoEleitoral ([municipioZona, local, secao])
    id_sec = _lista(itens[3][1])
    if len(id_sec) < 3:
        raise ErroDecodificacaoBU("identificação da seção incompleta")
    mun_zona = _lista(id_sec[0][1])
    municipio = _int(mun_zona[0][1])
    zona = _int(mun_zona[1][1])
    local = _int(id_sec[1][1])
    secao = _int(id_sec[2][1])

    # Campos seguintes da EntidadeBoletimUrna
    emissao = ""
    abertura = ""
    encerramento = ""
    comparecimento_urna = 0
    habilitados_biometria = 0
    liberados_codigo = 0
    habilitados_outros = 0
    seq_eleicoes: list[NoASN1] = []

    for tag, val in itens[4:]:
        if tag == (0, 27) and isinstance(val, bytes) and not emissao:
            emissao = _str(val)
        elif tag == (2, 0) and isinstance(val, list):
            datas = [_str(v) for t, v in val if t == (0, 27) and isinstance(v, bytes)]
            if len(datas) >= 2:
                abertura, encerramento = datas[0], datas[1]
            elif len(datas) == 1:
                abertura = datas[0]
        elif tag == (0, 2) and isinstance(val, bytes) and comparecimento_urna == 0:
            comparecimento_urna = _int(val)
        elif tag == (2, 1) and isinstance(val, list):
            ints = [_int(v) for t, v in val if t == (0, 2) and isinstance(v, bytes)]
            if len(ints) >= 3:
                habilitados_outros = ints[0]
                habilitados_biometria = ints[1]
                liberados_codigo = ints[2]
            elif len(ints) == 2:
                habilitados_biometria, liberados_codigo = ints[0], ints[1]
            elif len(ints) == 1:
                habilitados_biometria = ints[0]
        elif tag == (0, 16) and isinstance(val, list) and not seq_eleicoes:
            # A primeira SEQUENCE OF composta por elementos que começam com idEleicao [0:2]
            if val and val[0][0] == (0, 16) and isinstance(val[0][1], list):
                filhos0 = val[0][1]
                if len(filhos0) >= 5 and filhos0[0][0] == (0, 2):
                    seq_eleicoes = val

    cargos: dict[int, VotacaoCargo] = {}
    for _, ele_val in seq_eleicoes:
        ele_itens = _lista(ele_val)
        ints_cab = [
            _int(v) for t, v in ele_itens if t == (0, 2) and isinstance(v, bytes)
        ]
        id_eleicao = ints_cab[0] if len(ints_cab) >= 1 else 0
        aptos = ints_cab[1] if len(ints_cab) >= 2 else 0
        seqs = [v for t, v in ele_itens if t == (0, 16) and isinstance(v, list)]
        if not seqs:
            continue
        for _, res_vot_val in seqs[0]:
            rv = _lista(res_vot_val)
            comp_cargo = 0
            tot_list: list[NoASN1] = []
            for t_rv, v_rv in rv:
                if t_rv == (0, 2) and isinstance(v_rv, bytes):
                    comp_cargo = _int(v_rv)
                elif t_rv == (0, 16) and isinstance(v_rv, list):
                    tot_list = v_rv
            for _, tot_val in tot_list:
                tot_itens = _lista(tot_val)
                if not tot_itens:
                    continue
                cod_cargo = _int(tot_itens[0][1]) if isinstance(tot_itens[0][1], bytes) else 0
                votos_seq: list[NoASN1] = []
                for t_ti, v_ti in tot_itens[1:]:
                    if t_ti == (0, 16) and isinstance(v_ti, list):
                        votos_seq = v_ti
                        break
                nominais: dict[int, int] = {}
                brancos = 0
                nulos = 0
                legenda = 0
                anulados = 0
                for _, vot_val in votos_seq:
                    vot_itens = _lista(vot_val)
                    tp_voto = 0
                    qtd = 0
                    num_cand = 0
                    for t_v, v_v in vot_itens:
                        if t_v == (2, 1) and isinstance(v_v, bytes):
                            tp_voto = _int(v_v)
                        elif t_v == (2, 2) and isinstance(v_v, bytes):
                            qtd = _int(v_v)
                        elif t_v == (2, 3) and isinstance(v_v, list):
                            c_ints = [_int(x[1]) for x in v_v if x[0] == (0, 2) and isinstance(x[1], bytes)]
                            if c_ints:
                                num_cand = c_ints[0]
                    if tp_voto == 1:  # Nominal
                        nominais[num_cand] = nominais.get(num_cand, 0) + qtd
                    elif tp_voto == 2:  # Branco
                        brancos += qtd
                    elif tp_voto == 3:  # Nulo
                        nulos += qtd
                    elif tp_voto == 4:  # Legenda
                        legenda += qtd
                    else:
                        anulados += qtd
                total = sum(nominais.values()) + brancos + nulos + legenda + anulados
                cargos[cod_cargo] = VotacaoCargo(
                    eleicao=id_eleicao,
                    cargo=cod_cargo,
                    aptos=aptos,
                    comparecimento=comp_cargo,
                    nominais=nominais,
                    brancos=brancos,
                    nulos=nulos,
                    legenda=legenda,
                    anulados_apuracao=anulados,
                    total=total,
                )

    if comparecimento_urna == 0 and cargos:
        comparecimento_urna = max(c.comparecimento for c in cargos.values())

    return BoletimUrnaDecodificado(
        pleito=pleito,
        fase=fase,
        municipio=municipio,
        zona=zona,
        local=local,
        secao=secao,
        numero_interno_urna=numero_interno_urna,
        versao_votacao=versao_votacao,
        abertura=abertura,
        encerramento=encerramento,
        emissao=emissao,
        comparecimento_urna=comparecimento_urna,
        habilitados_biometria=habilitados_biometria,
        liberados_codigo=liberados_codigo,
        habilitados_outros=habilitados_outros,
        cargos=cargos,
    )
