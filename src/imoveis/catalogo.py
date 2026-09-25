"""Cliente da Fake Real Estate API + normalização para o agente."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import config

# Cidades da API mock usadas quando o lead cita regiões em PT-BR
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
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "AGENTE-SDR-F5/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=config.IMOVEIS_API_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"API de imóveis respondeu HTTP {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha ao consultar API de imóveis: {exc.reason}") from exc
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        return []
    return [_normalizar(x) for x in data if isinstance(x, dict)]


def buscar(
    catalogo: list[dict[str, Any]] | None = None,
    *,
    intencao: str | None = None,
    regiao: str | None = None,
    quartos_min: int | None = None,
    preco_max: float | None = None,
    limite: int = 5,
) -> list[dict[str, Any]]:
    """Busca imóveis na Fake Real Estate API (ou filtra lista já carregada)."""
    if catalogo is not None:
        itens = catalogo
    else:
        cidade = None
        if regiao:
            cidade = _REGIAO_PARA_CIDADE.get(regiao.strip().lower())
            if not cidade and regiao.strip():
                # tenta usar o texto como city da API
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
    moeda = imovel.get("moeda") or "USD"
    ops = ", ".join(imovel.get("operacao", []))
    return (
        f"{imovel.get('id')} — {imovel.get('endereco') or imovel.get('titulo')} ({ops})\n"
        f"  {imovel.get('cidade')}/{imovel.get('estado')} | "
        f"{imovel.get('quartos')} dorms | {imovel.get('area_m2')} sqft | "
        f"{moeda} {preco:,.0f}".replace(",", ".")
    )
