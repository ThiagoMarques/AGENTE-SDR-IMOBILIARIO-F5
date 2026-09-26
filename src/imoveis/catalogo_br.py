"""Catálogo sintético BR (POC) — preços e bairros realistas para demo."""
from __future__ import annotations

from typing import Any

# Imóveis didáticos em BRL alinhados às regiões que o agente reconhece.
CATALOGO_BR: list[dict[str, Any]] = [
    {
        "id": "BR-SP-001",
        "titulo": "Apartamento 2 dorms — Vila Mariana",
        "endereco": "Rua Domingos de Morais, 1200 — Vila Mariana",
        "cidade": "São Paulo",
        "estado": "SP",
        "regiao": "vila mariana",
        "bairro": "Vila Mariana",
        "tipo": "apartamento",
        "operacao": ["compra", "investimento"],
        "quartos": 2,
        "banheiros": 2,
        "area_m2": 68,
        "preco": 780_000,
        "moeda": "BRL",
        "descricao": "Apartamento iluminado perto do metrô.",
        "tags": ["metrô", "varanda"],
    },
    {
        "id": "BR-SP-002",
        "titulo": "Apartamento 3 dorms — Moema",
        "endereco": "Av. Ibirapuera, 2900 — Moema",
        "cidade": "São Paulo",
        "estado": "SP",
        "regiao": "moema",
        "bairro": "Moema",
        "tipo": "apartamento",
        "operacao": ["compra"],
        "quartos": 3,
        "banheiros": 3,
        "area_m2": 110,
        "preco": 1_450_000,
        "moeda": "BRL",
        "descricao": "Vista para o parque, 2 vagas.",
        "tags": ["2 vagas", "lazer"],
    },
    {
        "id": "BR-SP-003",
        "titulo": "Studio — Pinheiros",
        "endereco": "Rua dos Pinheiros, 850 — Pinheiros",
        "cidade": "São Paulo",
        "estado": "SP",
        "regiao": "pinheiros",
        "bairro": "Pinheiros",
        "tipo": "apartamento",
        "operacao": ["aluguel", "investimento"],
        "quartos": 1,
        "banheiros": 1,
        "area_m2": 32,
        "preco": 4_200,
        "moeda": "BRL",
        "descricao": "Studio mobiliado para locação.",
        "tags": ["mobiliado"],
    },
    {
        "id": "BR-SP-004",
        "titulo": "Apartamento 2 dorms — Zona Sul",
        "endereco": "Rua Vergueiro, 2100 — Zona Sul",
        "cidade": "São Paulo",
        "estado": "SP",
        "regiao": "zona sul",
        "bairro": "Vila Clementino",
        "tipo": "apartamento",
        "operacao": ["compra", "investimento"],
        "quartos": 2,
        "banheiros": 2,
        "area_m2": 72,
        "preco": 690_000,
        "moeda": "BRL",
        "descricao": "Pronto para morar, perto de comércio.",
        "tags": ["elevador"],
    },
    {
        "id": "BR-SP-005",
        "titulo": "Cobertura — Itaim Bibi",
        "endereco": "Rua João Cachoeira, 400 — Itaim Bibi",
        "cidade": "São Paulo",
        "estado": "SP",
        "regiao": "itaim bibi",
        "bairro": "Itaim Bibi",
        "tipo": "cobertura",
        "operacao": ["compra", "investimento"],
        "quartos": 3,
        "banheiros": 4,
        "area_m2": 180,
        "preco": 3_200_000,
        "moeda": "BRL",
        "descricao": "Cobertura com terraço gourmet.",
        "tags": ["terraço", "gourmet"],
    },
    {
        "id": "BR-SP-006",
        "titulo": "Apartamento 2 dorms — Brooklin",
        "endereco": "Av. Eng. Luís Carlos Berrini, 500 — Brooklin",
        "cidade": "São Paulo",
        "estado": "SP",
        "regiao": "brooklin",
        "bairro": "Brooklin",
        "tipo": "apartamento",
        "operacao": ["compra", "aluguel"],
        "quartos": 2,
        "banheiros": 2,
        "area_m2": 75,
        "preco": 920_000,
        "moeda": "BRL",
        "descricao": "Torre nova, lazer completo.",
        "tags": ["lazer"],
    },
    {
        "id": "BR-SP-007",
        "titulo": "Apartamento 3 dorms — Jardins",
        "endereco": "Alameda Santos, 1400 — Jardins",
        "cidade": "São Paulo",
        "estado": "SP",
        "regiao": "jardins",
        "bairro": "Jardins",
        "tipo": "apartamento",
        "operacao": ["compra"],
        "quartos": 3,
        "banheiros": 3,
        "area_m2": 140,
        "preco": 2_800_000,
        "moeda": "BRL",
        "descricao": "Alto padrão, 2 vagas.",
        "tags": ["alto padrão"],
    },
    {
        "id": "BR-SP-008",
        "titulo": "Kitnet — Centro",
        "endereco": "Av. São João, 300 — Centro",
        "cidade": "São Paulo",
        "estado": "SP",
        "regiao": "centro",
        "bairro": "República",
        "tipo": "kitnet",
        "operacao": ["aluguel", "investimento"],
        "quartos": 1,
        "banheiros": 1,
        "area_m2": 28,
        "preco": 2_100,
        "moeda": "BRL",
        "descricao": "Ideal para renda com locação.",
        "tags": ["renda"],
    },
    {
        "id": "BR-DF-001",
        "titulo": "Apartamento 2 dorms — Asa Sul",
        "endereco": "SQS 308 Bloco C — Asa Sul",
        "cidade": "Brasília",
        "estado": "DF",
        "regiao": "asa sul",
        "bairro": "Asa Sul",
        "tipo": "apartamento",
        "operacao": ["compra", "investimento"],
        "quartos": 2,
        "banheiros": 2,
        "area_m2": 80,
        "preco": 980_000,
        "moeda": "BRL",
        "descricao": "Quadra residencial, próximo ao comércio local.",
        "tags": ["asa sul"],
    },
    {
        "id": "BR-DF-002",
        "titulo": "Apartamento 3 dorms — Asa Norte",
        "endereco": "SQN 212 Bloco A — Asa Norte",
        "cidade": "Brasília",
        "estado": "DF",
        "regiao": "asa norte",
        "bairro": "Asa Norte",
        "tipo": "apartamento",
        "operacao": ["compra"],
        "quartos": 3,
        "banheiros": 2,
        "area_m2": 110,
        "preco": 1_250_000,
        "moeda": "BRL",
        "descricao": "Reformado, 1 vaga.",
        "tags": ["asa norte"],
    },
    {
        "id": "BR-DF-003",
        "titulo": "Casa 4 dorms — Lago Sul",
        "endereco": "SHIS QI 15 — Lago Sul",
        "cidade": "Brasília",
        "estado": "DF",
        "regiao": "lago sul",
        "bairro": "Lago Sul",
        "tipo": "casa",
        "operacao": ["compra", "investimento"],
        "quartos": 4,
        "banheiros": 5,
        "area_m2": 320,
        "preco": 4_500_000,
        "moeda": "BRL",
        "descricao": "Casa com área gourmet e piscina.",
        "tags": ["piscina"],
    },
    {
        "id": "BR-SP-009",
        "titulo": "Apartamento 2 dorms — Zona Oeste",
        "endereco": "Rua Heitor Penteado, 600 — Zona Oeste",
        "cidade": "São Paulo",
        "estado": "SP",
        "regiao": "zona oeste",
        "bairro": "Sumarezinho",
        "tipo": "apartamento",
        "operacao": ["compra", "aluguel"],
        "quartos": 2,
        "banheiros": 1,
        "area_m2": 65,
        "preco": 620_000,
        "moeda": "BRL",
        "descricao": "Boa localização para moradia ou renda.",
        "tags": ["zona oeste"],
    },
    {
        "id": "BR-SP-010",
        "titulo": "Apartamento 2 dorms — Zona Norte",
        "endereco": "Av. Braz Leme, 1500 — Zona Norte",
        "cidade": "São Paulo",
        "estado": "SP",
        "regiao": "zona norte",
        "bairro": "Santana",
        "tipo": "apartamento",
        "operacao": ["compra", "investimento"],
        "quartos": 2,
        "banheiros": 2,
        "area_m2": 70,
        "preco": 540_000,
        "moeda": "BRL",
        "descricao": "Próximo a escolas e transporte.",
        "tags": ["zona norte"],
    },
]

# Regiões “vizinhas” — como um corretor pensaria ao sugerir alternativa.
_VIZINHOS: dict[str, list[str]] = {
    "asa sul": ["asa norte", "lago sul", "lago norte"],
    "asa norte": ["asa sul", "lago norte", "lago sul"],
    "lago sul": ["asa sul", "lago norte", "asa norte"],
    "lago norte": ["asa norte", "lago sul", "asa sul"],
    "zona sul": ["vila mariana", "moema", "jardins", "brooklin", "itaim bibi"],
    "vila mariana": ["zona sul", "moema", "jardins"],
    "moema": ["vila mariana", "brooklin", "jardins", "zona sul"],
    "jardins": ["vila mariana", "moema", "pinheiros", "itaim bibi"],
    "pinheiros": ["jardins", "itaim bibi", "brooklin"],
    "itaim bibi": ["brooklin", "pinheiros", "jardins", "moema"],
    "brooklin": ["moema", "itaim bibi", "zona sul"],
    "centro": ["zona norte", "zona oeste"],
    "zona oeste": ["pinheiros", "centro"],
    "zona norte": ["centro"],
    "zona leste": ["centro", "zona norte"],
}

_ZONA_SUL_SP = {
    "zona sul",
    "vila mariana",
    "moema",
    "jardins",
    "itaim bibi",
    "brooklin",
}

_MAPA_INTENCAO = {
    "compra": "compra",
    "comprar": "compra",
    "aluguel": "aluguel",
    "alugar": "aluguel",
    "investimento": "investimento",
    "investir": "investimento",
}


def _ops_ok(imovel: dict[str, Any], intencao_n: str) -> bool:
    if not intencao_n:
        return True
    chave = _MAPA_INTENCAO.get(intencao_n, intencao_n)
    ops = [o.lower() for o in imovel.get("operacao", [])]
    return chave in ops


def _regiao_bate(imovel: dict[str, Any], regiao_n: str) -> bool:
    if not regiao_n:
        return True
    reg_im = str(imovel.get("regiao") or "").lower()
    bairro = str(imovel.get("bairro") or "").lower()
    if regiao_n == "zona sul":
        return reg_im in _ZONA_SUL_SP or regiao_n in bairro
    return regiao_n in reg_im or regiao_n in bairro


def _eh_vizinho(regiao_pedida: str, regiao_imovel: str) -> bool:
    if not regiao_pedida:
        return False
    viz = _VIZINHOS.get(regiao_pedida, [])
    if regiao_imovel in viz:
        return True
    if regiao_pedida == "zona sul" and regiao_imovel in _ZONA_SUL_SP:
        return True
    if regiao_imovel == "zona sul" and regiao_pedida in _ZONA_SUL_SP:
        return True
    return False


def _mesma_cidade_macro(regiao_a: str, regiao_b: str, cidade_im: str) -> bool:
    """Fallback leve: mesma praça (SP x DF) quando não há vizinhança direta."""
    df = {"asa sul", "asa norte", "lago sul", "lago norte"}
    if regiao_a in df and regiao_b in df:
        return True
    cidade = cidade_im.lower()
    if cidade in {"brasília", "brasilia"} and regiao_a in df:
        return True
    if cidade in {"são paulo", "sao paulo"}:
        sp = {
            "zona sul",
            "zona oeste",
            "zona norte",
            "zona leste",
            "centro",
            "moema",
            "pinheiros",
            "vila mariana",
            "itaim bibi",
            "brooklin",
            "jardins",
        }
        return regiao_a in sp and regiao_b in sp
    return False


def _motivos_aproximacao(
    *,
    regiao_n: str,
    quartos_min: int | None,
    preco_max: float | None,
    imovel: dict[str, Any],
    reg_exata: bool,
) -> list[str]:
    motivos: list[str] = []
    reg_im = str(imovel.get("regiao") or "").lower()
    q_im = int(imovel.get("quartos") or 0)
    preco = float(imovel.get("preco") or 0)

    if regiao_n and not reg_exata:
        if _eh_vizinho(regiao_n, reg_im):
            motivos.append(f"fica perto de {regiao_n} ({imovel.get('bairro') or reg_im})")
        else:
            motivos.append(f"está em {imovel.get('bairro') or reg_im}, na mesma praça")

    if quartos_min is not None and q_im != quartos_min:
        if q_im == quartos_min - 1:
            motivos.append(f"tem {q_im} quartos (um a menos do que você pediu)")
        elif q_im == quartos_min + 1:
            motivos.append(f"tem {q_im} quartos (um a mais)")
        else:
            motivos.append(f"tem {q_im} quartos")

    if preco_max is not None and preco > preco_max:
        pct = int(round((preco / preco_max - 1) * 100))
        motivos.append(f"fica cerca de {pct}% acima do teto que você falou")
    elif preco_max is not None and preco <= preco_max * 0.85:
        motivos.append("encaixa com folga no orçamento")

    if not motivos and not reg_exata:
        motivos.append("é a opção mais próxima do que você descreveu")
    return motivos


def _score_aproximado(
    imovel: dict[str, Any],
    *,
    regiao_n: str,
    quartos_min: int | None,
    preco_max: float | None,
) -> tuple[float, list[str], bool]:
    """Menor score = melhor. Retorna (score, motivos, regiao_exata)."""
    reg_im = str(imovel.get("regiao") or "").lower()
    q_im = int(imovel.get("quartos") or 0)
    preco = float(imovel.get("preco") or 0)
    cidade = str(imovel.get("cidade") or "")

    reg_exata = _regiao_bate(imovel, regiao_n) if regiao_n else True
    score = 0.0

    if regiao_n:
        if reg_exata:
            score += 0
        elif _eh_vizinho(regiao_n, reg_im):
            score += 12
        elif _mesma_cidade_macro(regiao_n, reg_im, cidade):
            score += 28
        else:
            score += 80

    if quartos_min is not None:
        diff = abs(q_im - quartos_min)
        if diff == 0:
            score += 0
        elif diff == 1:
            score += 10
        elif diff == 2:
            score += 22
        else:
            score += 40
        if q_im < quartos_min:
            score += 1

    if preco_max is not None:
        if preco <= preco_max:
            score += 0
        elif preco <= preco_max * 1.15:
            score += 8
        elif preco <= preco_max * 1.35:
            score += 18
        else:
            score += 45

    motivos = _motivos_aproximacao(
        regiao_n=regiao_n,
        quartos_min=quartos_min,
        preco_max=preco_max,
        imovel=imovel,
        reg_exata=reg_exata,
    )
    return score, motivos, reg_exata


def _filtrar_exato(
    *,
    intencao: str | None,
    regiao: str | None,
    quartos_min: int | None,
    preco_max: float | None,
    limite: int,
) -> list[dict[str, Any]]:
    intencao_n = (intencao or "").strip().lower()
    regiao_n = (regiao or "").strip().lower()
    resultado: list[dict[str, Any]] = []
    for imovel in CATALOGO_BR:
        if not _ops_ok(imovel, intencao_n):
            continue
        if not _regiao_bate(imovel, regiao_n):
            continue
        if quartos_min is not None and int(imovel.get("quartos") or 0) < quartos_min:
            continue
        if preco_max is not None and float(imovel.get("preco") or 0) > preco_max:
            continue
        item = dict(imovel)
        item["match"] = "exato"
        item["match_motivo"] = ""
        resultado.append(item)
        if len(resultado) >= limite:
            break
    return resultado


def _filtrar_aproximado(
    *,
    intencao: str | None,
    regiao: str | None,
    quartos_min: int | None,
    preco_max: float | None,
    limite: int,
) -> tuple[list[dict[str, Any]], str]:
    intencao_n = (intencao or "").strip().lower()
    regiao_n = (regiao or "").strip().lower()
    ranqueados: list[tuple[float, dict[str, Any]]] = []

    for imovel in CATALOGO_BR:
        if not _ops_ok(imovel, intencao_n):
            continue
        q_im = int(imovel.get("quartos") or 0)
        preco = float(imovel.get("preco") or 0)
        if quartos_min is not None and abs(q_im - quartos_min) > 1:
            reg_im = str(imovel.get("regiao") or "").lower()
            if not (_regiao_bate(imovel, regiao_n) or _eh_vizinho(regiao_n, reg_im)):
                continue
            if abs(q_im - quartos_min) > 2:
                continue
        if preco_max is not None and preco > preco_max * 1.35:
            continue

        score, motivos, _ = _score_aproximado(
            imovel,
            regiao_n=regiao_n,
            quartos_min=quartos_min,
            preco_max=preco_max,
        )
        if score >= 70:
            continue
        item = dict(imovel)
        item["match"] = "aproximado"
        item["match_motivo"] = "; ".join(motivos)
        ranqueados.append((score, item))

    ranqueados.sort(key=lambda x: (x[0], float(x[1].get("preco") or 0)))
    top = [it for _, it in ranqueados[: max(limite * 2, 6)]]
    if not top:
        return [], ""
    # Evita “alternativa” absurdamente cara vs a melhor opção (senso de corretor)
    if preco_max is None and top:
        ref = float(top[0].get("preco") or 0) or 1.0
        filtrados = [it for it in top if float(it.get("preco") or 0) <= ref * 2.2]
        top = filtrados or top[:1]
    top = top[:limite]
    primeiro = top[0].get("match_motivo") or "opções próximas do que você pediu"
    return top, str(primeiro)


def _max_quartos_catalogo(
    *,
    intencao: str | None = None,
    regiao: str | None = None,
) -> int:
    intencao_n = (intencao or "").strip().lower()
    regiao_n = (regiao or "").strip().lower()
    mx = 0
    for imovel in CATALOGO_BR:
        if not _ops_ok(imovel, intencao_n):
            continue
        if regiao_n and not (
            _regiao_bate(imovel, regiao_n)
            or _eh_vizinho(regiao_n, str(imovel.get("regiao") or "").lower())
        ):
            continue
        mx = max(mx, int(imovel.get("quartos") or 0))
    if mx == 0:
        for imovel in CATALOGO_BR:
            if _ops_ok(imovel, intencao_n):
                mx = max(mx, int(imovel.get("quartos") or 0))
    return mx


def _fallback_estoque(
    *,
    intencao: str | None,
    regiao: str | None,
    preco_max: float | None,
    limite: int,
    quartos_pedidos: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Último recurso: mostra o que realmente existe na região/vizinhança,
    sem inventar tipologias. Usado quando o pedido foge do estoque (ex.: 8–9 quartos).
    """
    intencao_n = (intencao or "").strip().lower()
    regiao_n = (regiao or "").strip().lower()
    candidatos: list[tuple[float, dict[str, Any]]] = []

    for imovel in CATALOGO_BR:
        if not _ops_ok(imovel, intencao_n):
            continue
        reg_im = str(imovel.get("regiao") or "").lower()
        preco = float(imovel.get("preco") or 0)
        if preco_max is not None and preco > preco_max * 1.35:
            continue
        if regiao_n:
            if _regiao_bate(imovel, regiao_n):
                score = 0.0
            elif _eh_vizinho(regiao_n, reg_im):
                score = 10.0
            else:
                continue
        else:
            score = 5.0
        # Preferir mais quartos quando o pedido era alto
        if quartos_pedidos is not None:
            score += abs(int(imovel.get("quartos") or 0) - min(quartos_pedidos, 4)) * 0.5
        item = dict(imovel)
        item["match"] = "aproximado"
        q = int(imovel.get("quartos") or 0)
        item["match_motivo"] = (
            f"disponível agora: {q} quarto" + ("s" if q != 1 else "")
            + f" em {imovel.get('bairro') or reg_im}"
        )
        candidatos.append((score, item))

    candidatos.sort(key=lambda x: (x[0], float(x[1].get("preco") or 0)))
    top = [it for _, it in candidatos[:limite]]
    if not top:
        return [], ""
    mx = max(int(i.get("quartos") or 0) for i in top)
    if quartos_pedidos and quartos_pedidos > mx:
        motivo = (
            f"não tenho imóvel com {quartos_pedidos} quartos; "
            f"o máximo que tenho por aqui agora é {mx} quarto"
            + ("s" if mx != 1 else "")
        )
    elif regiao_n:
        motivo = f"o que tenho disponível perto de {regiao_n}"
    else:
        motivo = "o que tenho disponível agora no estoque"
    return top, motivo


def buscar_br(
    *,
    intencao: str | None = None,
    regiao: str | None = None,
    quartos_min: int | None = None,
    preco_max: float | None = None,
    limite: int = 5,
    aproximar: bool = True,
) -> list[dict[str, Any]]:
    """Compat: devolve só a lista (exato ou aproximado)."""
    out = buscar_br_resultado(
        intencao=intencao,
        regiao=regiao,
        quartos_min=quartos_min,
        preco_max=preco_max,
        limite=limite,
        aproximar=aproximar,
    )
    return out["imoveis"]


def buscar_br_resultado(
    *,
    intencao: str | None = None,
    regiao: str | None = None,
    quartos_min: int | None = None,
    preco_max: float | None = None,
    limite: int = 5,
    aproximar: bool = True,
) -> dict[str, Any]:
    """
    Busca com fallback humano:
    1) match exato
    2) sugestões próximas (±1 quarto, vizinhança)
    3) estoque real da região (quando o pedido foge do inventário)
    """
    exatos = _filtrar_exato(
        intencao=intencao,
        regiao=regiao,
        quartos_min=quartos_min,
        preco_max=preco_max,
        limite=limite,
    )
    if exatos:
        return {
            "imoveis": exatos,
            "match": "exato",
            "motivo": "",
        }
    if not aproximar:
        return {"imoveis": [], "match": "vazio", "motivo": ""}

    max_q = _max_quartos_catalogo(intencao=intencao, regiao=regiao)
    pedido_fora = (
        quartos_min is not None and max_q > 0 and int(quartos_min) > max_q + 1
    )

    if not pedido_fora:
        approx, motivo = _filtrar_aproximado(
            intencao=intencao,
            regiao=regiao,
            quartos_min=quartos_min,
            preco_max=preco_max,
            limite=limite,
        )
        if approx:
            return {
                "imoveis": approx,
                "match": "aproximado",
                "motivo": motivo,
            }

    estoque, motivo_e = _fallback_estoque(
        intencao=intencao,
        regiao=regiao,
        preco_max=preco_max,
        limite=limite,
        quartos_pedidos=int(quartos_min) if quartos_min is not None else None,
    )
    if estoque:
        return {
            "imoveis": estoque,
            "match": "aproximado",
            "motivo": motivo_e,
        }
    return {"imoveis": [], "match": "vazio", "motivo": ""}
