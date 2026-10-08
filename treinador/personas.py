"""Leads simulados.

`descricao` e `objetivo` guiam o LLM que interpreta a persona. `roteiro` é usado
sem LLM (ou com --sem-llm): as mensagens são enviadas na ordem, sem reagir ao agente.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Persona:
    id: str
    descricao: str
    objetivo: str
    roteiro: list[str] = field(default_factory=list)
    nome: str = ""

    @property
    def rotulo(self) -> str:
        return self.nome or self.id.replace("_", " ")


PERSONAS: list[Persona] = [
    Persona(
        id="investidor_direto",
        descricao="Investidor objetivo, frases curtas, sabe o que quer.",
        objetivo="Investir cerca de R$ 200 mil buscando renda de aluguel, retorno de uns 6% ao ano, e ver opções.",
        roteiro=["quero investir", "200 mil", "renda", "uns 6% ao ano", "quero marcar uma visita"],
    ),
    Persona(
        id="investidor_prazo",
        descricao="Investidor que confunde prazo com retorno e responde de forma vaga.",
        objetivo="Investir R$ 500 mil pensando em valorização; quando perguntarem o retorno, responde primeiro com o prazo ('em 3 anos').",
        roteiro=["oi", "quero investir", "500 mil", "valorizar", "em 3 anos", "sei la, uns 10%"],
    ),
    Persona(
        id="inquilina_digita_errado",
        descricao="Pessoa no celular, digita com erros e sem acentos.",
        objetivo="Alugar um apartamento de 1 quarto na Zona Sul de São Paulo até R$ 2.500.",
        roteiro=["quero alugr um ap", "zuna sul", "ate 2500", "1 quarto", "urgente"],
    ),
    Persona(
        id="muda_de_ideia",
        descricao="Comprador indeciso que muda região e valor no meio da conversa.",
        objetivo="Começa querendo comprar na Zona Sul até 800 mil, muda para a Zona Leste e depois aumenta o valor para 1 milhão.",
        roteiro=["quero comprar na zona sul", "até 800 mil", "ah, não, muda pra zona leste", "2 quartos",
                 "sem pressa", "na verdade posso ir até 1 milhão"],
    ),
    Persona(
        id="so_responde_sim",
        descricao="Lead lacônico que responde quase tudo com 'sim', 'ok' ou 'pode ser'.",
        objetivo="Comprar algo barato na Asa Sul (Brasília), até R$ 200 mil, 1 quarto. Responde 'sim' às sugestões do agente.",
        roteiro=["quero comprar na asa sul", "200 mil", "1 quarto", "sem pressa", "sim", "sim", "ok"],
    ),
    Persona(
        id="curioso_duvidas",
        descricao="Comprador de primeira viagem, faz perguntas no meio do fluxo.",
        objetivo="Comprar em Moema até 1,5 milhão, 2 quartos; no caminho pergunta sobre ITBI, FGTS e condomínio.",
        roteiro=["quero comprar meu primeiro apartamento", "o que é ITBI?", "moema", "posso usar o FGTS?",
                 "até 1,5 milhão", "2 quartos", "quanto é o condomínio?", "médio prazo"],
    ),
    Persona(
        id="tudo_de_uma_vez",
        descricao="Pessoa eficiente que manda tudo numa mensagem só e quer agendar logo.",
        objetivo="Comprar 3 quartos em Moema até 1 milhão, sem pressa, e marcar visita no primeiro horário.",
        roteiro=["3 quartos em moema até 1 milhão, quero comprar, sem pressa", "o primeiro",
                 "meu nome é Carla", "carla.teste@example.com"],
    ),
    Persona(
        id="fora_de_escopo",
        descricao="Lead que se distrai e puxa assuntos fora do tema.",
        objetivo="Alugar na Asa Norte até R$ 3 mil, mas pergunta da previsão do tempo e de futebol no meio.",
        roteiro=["quero alugar na asa norte", "vai chover amanhã?", "3 mil", "quem ganhou o jogo ontem?",
                 "2 quartos", "pra este mês"],
    ),
    Persona(
        id="agenda_e_remarca",
        descricao="Lead decidido que agenda, erra o e-mail e depois remarca.",
        objetivo="Comprar 2 quartos no Brooklin até 1,2 milhão, marcar visita, informar e-mail com domínio errado (gmial.com) e depois remarcar.",
        roteiro=["quero comprar no brooklin", "1,2 milhão", "2 quartos", "logo", "quero agendar uma visita",
                 "o segundo", "joao.teste@gmial.com", "sim", "preciso remarcar"],
    ),
    Persona(
        id="monossilabico",
        descricao="Responde só com uma palavra ou número.",
        objetivo="Comprar no centro de São Paulo, até 500 mil, 2 quartos, prazo curto.",
        roteiro=["compra", "centro", "500", "2", "logo"],
    ),
]


def por_id(ids: list[str] | None) -> list[Persona]:
    """Personas fixas e contextos salvos pelo usuário; sem ids, só as fixas."""
    if not ids:
        return list(PERSONAS)
    from treinador.contextos import como_persona, listar

    mapa = {p.id: p for p in PERSONAS} | {c["id"]: como_persona(c) for c in listar()}
    desconhecidas = [i for i in ids if i not in mapa]
    if desconhecidas:
        raise SystemExit(f"Personas desconhecidas: {', '.join(desconhecidas)}. Disponíveis: {', '.join(mapa)}")
    return [mapa[i] for i in ids]
