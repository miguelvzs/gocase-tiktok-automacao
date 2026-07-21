"""Leitura de tendências reais, e a triagem que as torna utilizáveis.

O projeto se chama Radar de Tendência e, até aqui, lia um catálogo fixo. Este
módulo liga o sistema ao mundo: busca o que o Brasil está pesquisando agora no
Google Trends e decide o que disso vira estampa.

A parte interessante não é buscar — é RECUSAR. Uma leitura real devolveu:

    8 de janeiro · deltan dallagnol · banco master · tribunal de contas
    liga dos campeões · fenerbahçe · mg-188 · bianca andrade

Política, processo judicial, notícia financeira, futebol de clube, provável
acidente rodoviário e nome de pessoa. Nenhum vira capinha, e vários violam
diretamente as proibições da marca. Um radar ingênuo tentaria desenhar o 8 de
janeiro.

Então a fonte real entra com uma triagem dura na frente, e o catálogo curado
continua existindo como destino padrão — não como plano B envergonhado, mas
porque na maioria das leituras nada passa. A automação segue publicando de
qualquer jeito; o que muda é a origem do assunto, registrada no relatório.

Sem chave de IA, o módulo nem tenta: devolve vazio e o catálogo assume.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

log = logging.getLogger(__name__)

FONTE = "https://trends.google.com/trending/rss"
NS = {"ht": "https://trends.google.com/trending/rss"}

# Curto de propósito: é a primeira etapa do pipeline e não pode segurar a
# execução. Estourou, o catálogo assume.
TEMPO_LIMITE = 12.0

ESQUEMA = {
    "type": "object",
    "properties": {
        "aprovados": {
            "type": "array",
            "description": (
                "Somente as buscas que passam em TODOS os critérios. Vazio é uma "
                "resposta correta e frequente."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "busca": {
                        "type": "string",
                        "description": "O termo original, copiado sem alteração.",
                    },
                    "tema": {
                        "type": "string",
                        "description": (
                            "O assunto reescrito como tema de estampa, em "
                            "português, sem citar pessoas, marcas ou clubes."
                        ),
                    },
                    "publico": {
                        "type": "string",
                        "description": "Faixa etária e perfil, ex.: '18-26, música'.",
                    },
                    "estetica": {
                        "type": "string",
                        "description": (
                            "A linguagem visual em termos que um ilustrador "
                            "executaria: formas, texturas, paleta, composição. "
                            "Duas a quatro frases."
                        ),
                    },
                },
                "required": ["busca", "tema", "publico", "estetica"],
                "additionalProperties": False,
            },
        },
        "recusados": {
            "type": "array",
            "description": "Cada busca barrada, com o motivo em poucas palavras.",
            "items": {
                "type": "object",
                "properties": {
                    "busca": {"type": "string"},
                    "motivo": {"type": "string"},
                },
                "required": ["busca", "motivo"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["aprovados", "recusados"],
    "additionalProperties": False,
}

SISTEMA = (
    "Você faz a triagem de buscas em alta para uma marca que imprime estampas "
    "em capinha de celular.\n\n"
    "Sua função principal é RECUSAR. A maioria do que está em alta é notícia, e "
    "notícia não vira estampa. Aprovar algo inadequado custa muito mais caro do "
    "que deixar passar uma oportunidade: devolver lista vazia é resultado "
    "correto e esperado.\n\n"
    "RECUSE sem exceção:\n"
    "- Política, eleição, governo, processo judicial, investigação\n"
    "- Tragédia, acidente, crime, morte, desastre, doença\n"
    "- Pessoa real, influenciador, artista, atleta — nome de gente não se estampa\n"
    "- Marca, empresa, banco, produto de terceiro\n"
    "- Clube de futebol, seleção, competição com dono — é propriedade de marca\n"
    "- Religião e saúde\n"
    "- Notícia factual sem carga visual própria\n\n"
    "APROVE somente o que cumpre as quatro condições:\n"
    "1. É estética, cultural ou sazonal — não é notícia.\n"
    "2. Tem forma, cor ou textura próprias que um ilustrador desenharia.\n"
    "3. Interessa a alguém de 16 a 32 anos.\n"
    "4. A pessoa carregaria isso no bolso o dia inteiro. É roupa, não manchete.\n\n"
    "Ao aprovar, reescreva o assunto como TEMA DE ESTAMPA, sem citar o nome "
    "próprio que o originou. Uma alta em 'festival tal' não vira o festival: "
    "vira a estética de festival de verão. Se sobrar qualquer dúvida sobre a "
    "adequação, recuse."
)


def _buscar(regiao: str) -> list[str]:
    """Termos em alta agora, direto do feed público do Google Trends."""
    resposta = httpx.get(
        FONTE, params={"geo": regiao}, timeout=TEMPO_LIMITE,
        headers={"User-Agent": "radar-tendencia-gocase/1.0"},
    )
    resposta.raise_for_status()
    raiz = ET.fromstring(resposta.text)
    termos = []
    for item in raiz.findall(".//item"):
        titulo = (item.findtext("title") or "").strip()
        if titulo:
            trafego = (item.findtext("ht:approx_traffic", "", NS) or "").strip()
            termos.append(f"{titulo} ({trafego})" if trafego else titulo)
    return termos


def _identificador(tema: str) -> str:
    """Chave estável para o histórico de combinações já usadas."""
    limpo = re.sub(r"[^a-z0-9]+", "-", tema.lower().strip())[:40]
    return f"radar-{limpo.strip('-') or 'tendencia'}"


def buscar_sinais(
    *,
    api_key: str | None,
    modelo: str,
    regiao: str = "BR",
    maximo: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Devolve `(sinais_aprovados, recusas)`.

    Nunca levanta exceção: qualquer falha vira lista vazia, e quem chama segue
    com o catálogo. Uma fonte externa instável não pode derrubar a publicação.
    """
    if not api_key:
        return [], []

    try:
        termos = _buscar(regiao)
    except Exception as erro:
        log.warning("Radar: fonte de tendências indisponível (%s).", erro)
        return [], []

    if not termos:
        return [], []
    log.info("Radar: %d buscas em alta em %s.", len(termos), regiao)

    try:
        import anthropic

        cliente = anthropic.Anthropic(api_key=api_key)
        resposta = cliente.messages.create(
            model=modelo,
            max_tokens=2000,
            system=SISTEMA,
            messages=[
                {
                    "role": "user",
                    "content": "Buscas em alta agora:\n" + "\n".join(f"- {t}" for t in termos),
                }
            ],
            output_config={
                "format": {"type": "json_schema", "schema": ESQUEMA},
                # Triagem é classificação, não criação: o esforço extra não
                # melhora o julgamento e atrasa a primeira etapa do pipeline.
                "effort": "low",
            },
        )
        dados = json.loads(next(b.text for b in resposta.content if b.type == "text"))
    except Exception as erro:
        log.warning("Radar: triagem falhou (%s); seguindo com o catálogo.", erro)
        return [], []

    recusados = dados.get("recusados", [])
    aprovados = []
    for item in dados.get("aprovados", [])[:maximo]:
        tema = (item.get("tema") or "").strip()
        if not tema:
            continue
        aprovados.append(
            {
                "id": _identificador(tema),
                "tema": tema,
                "publico": (item.get("publico") or "16-32").strip(),
                "estetica": (item.get("estetica") or "").strip(),
                "origem": "radar",
                "busca": (item.get("busca") or "").strip(),
            }
        )

    log.info(
        "Radar: %d aprovados, %d recusados. %s",
        len(aprovados),
        len(recusados),
        "; ".join(f"{r.get('busca')}: {r.get('motivo')}" for r in recusados[:4]),
    )
    return aprovados, recusados
