"""Cliente de catálogo de imóveis: preferência BR (POC) + Fake API opcional."""
from __future__ import annotations

from typing import Any

import requests

import config
from src.imoveis.catalogo_br import buscar_br_resultado

# Cidades da API mock (EUA) — só se IMOVEIS_SOURCE=fake
_REGIAO_PARA_CIDADE = {
    "zona sul": "Austin",
    "zona oeste": "Austin",
    "zona norte": "Springfield",
    "zona leste": "Springfield",
    "centro": "Austin",
    "moema": "Austin",
    "pinheiros": "Austin",
    "vila mariana": "Austin",
    "itaim": "Austin",
    "austin": "Austin",
    "springfield": "Springfield",
}


def _fonte() -> str:
    return (getattr(config, "IMOVEIS_SOURCE", None) or "br").strip().lower()


def _tipo_api(intencao: str | None) -> str | None:
    if not intencao:
        return None
    chave = intencao.strip().lower()
    if chave in {"aluguel", "alugar", "rent"}:
        return "rent"
    if chave in {"compra", "comprar", "investimento", "investir", "sale"}:
        return "sale"
    return None


def _normalizar(item: dict[str, Any]) -> dict[str, Any]:
    tipo = (item.get("type") or "sale").lower()
    operacao = ["aluguel"] if tipo == "rent" else ["compra"]
    if tipo == "sale" and float(item.get("price") or 0) <= 450_000:
        operacao.append("investimento")
    return {
        "id": item.get("id"),
        "titulo": f"{item.get('property_type', 'imovel')} — {item.get('address', '')}",
        "endereco": item.get("address"),
        "cidade": item.get("city"),
        "estado": item.get("state"),
        "regiao": item.get("city_market") or item.get("city"),
        "bairro": item.get("city"),
        "tipo": item.get("property_type"),
        "operacao": operacao,
        "quartos": item.get("beds"),
        "banheiros": item.get("baths"),
        "area_m2": item.get("sqft"),
        "preco": item.get("price"),
        "moeda": item.get("currency") or "USD",
        "descricao": item.get("description"),
        "tags": item.get("features") or [],
        "agente": item.get("agent") or {},
        "bruto": item,
    }


def _get_listings(params: dict[str, Any]) -> list[dict[str, Any]]:
    query = {k: v for k, v in params.items() if v is not None and v != ""}
    url = f"{config.IMOVEIS_API_BASE}/listings"
    try:
        resp = requests.get(
            url,
            params=query,
            headers={"Accept": "application/json", "User-Agent": "AGENTE-SDR-F5/1.0"},
            timeout=config.IMOVEIS_API_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "?"
        raise RuntimeError(f"API de imóveis respondeu HTTP {code}: {url}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Falha ao consultar API de imóveis: {exc}") from exc
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        return []
    return [_normalizar(x) for x in data if isinstance(x, dict)]


def buscar_resultado(
    catalogo: list[dict[str, Any]] | None = None,
    *,
    intencao: str | None = None,
    regiao: str | None = None,
    quartos_min: int | None = None,
    preco_max: float | None = None,
    limite: int = 5,
    aproximar: bool = True,
) -> dict[str, Any]:
    """Busca com metadados de match (exato | aproximado | vazio)."""
    if catalogo is not None:
        itens = _filtrar(
            catalogo,
            intencao=intencao,
            quartos_min=quartos_min,
            preco_max=preco_max,
            limite=limite,
        )
        for im in itens:
            im.setdefault("match", "exato")
            im.setdefault("match_motivo", "")
        return {
            "imoveis": itens,
            "match": "exato" if itens else "vazio",
            "motivo": "",
        }

    if _fonte() != "fake":
        return buscar_br_resultado(
            intencao=intencao,
            regiao=regiao,
            quartos_min=quartos_min,
            preco_max=preco_max,
            limite=limite,
            aproximar=aproximar,
        )

    cidade = None
    if regiao:
        cidade = _REGIAO_PARA_CIDADE.get(regiao.strip().lower())
        if not cidade and regiao.strip():
            cidade = regiao.strip().title()
    params: dict[str, Any] = {
        "page": 1,
        "per_page": min(max(limite * 3, 5), 50),
        "type": _tipo_api(intencao),
        "city": cidade,
        "beds_min": quartos_min,
        "price_max": int(preco_max) if preco_max is not None else None,
    }
    itens = _get_listings(params)
    filtrados = _filtrar(
        itens,
        intencao=intencao,
        quartos_min=quartos_min,
        preco_max=preco_max,
        limite=limite,
    )
    # Fallback Fake API: relaxa leito/preço se veio vazio
    if not filtrados and aproximar:
        filtrados = _filtrar(
            itens,
            intencao=intencao,
            quartos_min=(quartos_min - 1) if quartos_min and quartos_min > 1 else quartos_min,
            preco_max=(preco_max * 1.2) if preco_max else None,
            limite=limite,
        )
        for im in filtrados:
            im["match"] = "aproximado"
            im["match_motivo"] = "ajuste leve de quartos/orçamento na API externa"
        return {
            "imoveis": filtrados,
            "match": "aproximado" if filtrados else "vazio",
            "motivo": filtrados[0].get("match_motivo", "") if filtrados else "",
        }
    for im in filtrados:
        im.setdefault("match", "exato")
        im.setdefault("match_motivo", "")
    return {
        "imoveis": filtrados,
        "match": "exato" if filtrados else "vazio",
        "motivo": "",
    }


def buscar(
    catalogo: list[dict[str, Any]] | None = None,
    *,
    intencao: str | None = None,
    regiao: str | None = None,
    quartos_min: int | None = None,
    preco_max: float | None = None,
    limite: int = 5,
) -> list[dict[str, Any]]:
    """Busca imóveis: catálogo BR por padrão; Fake API se IMOVEIS_SOURCE=fake."""
    return buscar_resultado(
        catalogo,
        intencao=intencao,
        regiao=regiao,
        quartos_min=quartos_min,
        preco_max=preco_max,
        limite=limite,
    )["imoveis"]


def _filtrar(
    itens: list[dict[str, Any]],
    *,
    intencao: str | None,
    quartos_min: int | None,
    preco_max: float | None,
    limite: int,
) -> list[dict[str, Any]]:
    intencao_n = (intencao or "").strip().lower()
    resultado: list[dict[str, Any]] = []
    for imovel in itens:
        ops = [o.lower() for o in imovel.get("operacao", [])]
        if intencao_n:
            mapa = {
                "compra": "compra",
                "comprar": "compra",
                "aluguel": "aluguel",
                "alugar": "aluguel",
                "investimento": "investimento",
                "investir": "investimento",
            }
            chave = mapa.get(intencao_n, intencao_n)
            if chave not in ops:
                continue
        if quartos_min is not None and int(imovel.get("quartos") or 0) < quartos_min:
            continue
        if preco_max is not None and float(imovel.get("preco") or 0) > preco_max:
            continue
        resultado.append(imovel)
        if len(resultado) >= limite:
            break
    return resultado


def formatar_imovel(imovel: dict[str, Any]) -> str:
    preco = imovel.get("preco")
    moeda = imovel.get("moeda") or "BRL"
    ops = ", ".join(imovel.get("operacao", []))
    area = imovel.get("area_m2")
    unidade_area = "m²" if moeda == "BRL" else "sqft"
    preco_txt = f"{preco:,.0f}".replace(",", ".")
    quartos = imovel.get("quartos")
    return (
        f"{imovel.get('id')} — {imovel.get('endereco') or imovel.get('titulo')} ({ops})\n"
        f"  {imovel.get('cidade')}/{imovel.get('estado')} | "
        f"{quartos} quarto{'' if quartos == 1 else 's'} | {area} {unidade_area} | "
        f"{moeda} {preco_txt}"
    )
