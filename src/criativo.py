"""Camada de IA: conceito de arte, legenda e hashtags.

Espelha o "AI node to create Social Media posts" do vídeo de referência.

Duas decisões de engenharia que valem registro:

1. **Structured outputs, não "responda em JSON".** O formato é imposto pela API
   via `output_config.format`, com schema JSON. Pedir JSON no prompt e torcer
   pelo melhor é o modo comum de quebrar pipeline em produção.

2. **Guardrails de marca verificados por código.** As proibições do
   `config.yaml` entram no prompt *e* são conferidas depois da geração. Modelo
   de linguagem é bom a seguir instrução, mas não é mecanismo de garantia —
   se o texto violar uma regra, o pipeline barra em vez de publicar.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

import anthropic

log = logging.getLogger(__name__)

# Termos que denunciam cada proibição do config.yaml. A checagem é
# deliberadamente conservadora: prefere barrar e pedir nova geração a deixar
# passar algo que a marca não autorizou.
#
# Os padrões são escritos SEM acento e o texto é normalizado antes da
# comparação. Sem isso, "revolucionária" seria barrado e "revolucionaria"
# passaria — e um modelo de linguagem produz as duas formas.
PADROES_PROIBIDOS: dict[str, str] = {
    "promessa de prazo de entrega": (
        r"\b(entrega|chega|receb\w+)\s+(em|ate)\s+\d"
        r"|\b\d+\s*(dias?|horas?)\s+(uteis|para|de entrega)"
    ),
    "preço ou desconto": (
        r"(R\$\s*\d|\b\d+\s*%\s*(off|de desconto)|\bgratis\b|\bpromoc)"
    ),
    "comparação direta com concorrente": (
        r"\b(melhor que|superior a|ao contrario d[oa]s? (concorrent|outr))"
    ),
    "superlativo sem lastro": (
        # Cobre "a mais bonita do mundo" e também as formas sintéticas
        # ("a melhor do mundo"), que não passam pela palavra "mais".
        r"\b[oa] (mais \w+|melhor|maior|pior|top) d[oe] (mundo|brasil|todos|mercado)"
        r"|\b(imbativel|inigualavel|revolucionari|incrivelmente"
        r"|perfeicao absoluta|unic[oa] no mercado|sem igual)"
    ),
    # Prefixos precisam de \w* no fim; um \b fechando o grupo impediria
    # "eleic" de casar com "eleicao". "cura" fica ancorado dos dois lados
    # para não barrar "curadoria", que é palavra legítima de marketing.
    "menção a saúde, política ou religião": (
        r"\bcura\b|\b(tratamento medic\w*|eleic[ao]\w*|deputad\w*|senador\w*"
        r"|president[ea] d[ao]|igreja\w*|orac(ao|oes)\w*|reza\b|abencoa\w*)"
    ),
}


def _normalizar(texto: str) -> str:
    """Minúsculas sem acento, para que a checagem não dependa de ortografia."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn").lower()

ESQUEMA = {
    "type": "object",
    "properties": {
        "conceito_arte": {
            "type": "string",
            "description": (
                "Prompt em inglês para gerar a ARTE que será impressa na "
                "capinha. Descreve estilo, composição e cores. Sem texto, sem "
                "letras, sem logotipo — arte gráfica pura."
            ),
        },
        "gancho": {
            "type": "string",
            "description": (
                "Frase que aparece SOBRE o vídeo, até 60 caracteres. É lida em "
                "menos de um segundo, enquanto o dedo já está subindo — precisa "
                "criar vontade de ter a capinha, não contar a história do "
                "padrão. Fale do produto ou de quem o usa. "
                "Ruim: 'Capinha com estampa botânica' — o vídeo já mostra isso. "
                "Ruim: 'O piso da casa da minha avó virou capinha' — vende "
                "curiosidade sobre a origem, não a capinha. "
                "Bom: 'A estampa que todo mundo vai querer semana que vem'. "
                "NÃO comece com 'A capinha que' nem com 'A estampa que' — é a "
                "saída mais óbvia e vira molde quando dois posts saem na mesma "
                "semana. Varie a entrada: comece pelo público, por uma cena de "
                "uso, por uma afirmação seca ou por um contraste. "
                "Sem ponto final, sem emoji, sem hashtag."
            ),
        },
        "legenda": {
            "type": "string",
            "description": (
                "Legenda do post, 120 a 250 caracteres, sem hashtags. "
                "ESTRUTURA em três partes separadas por quebra de linha "
                "(\\n): "
                "(1) uma frase curta que continue o gancho em vez de repeti-lo — "
                "é a única linha visível antes do 'ver mais'; "
                "(2) uma frase sobre a CAPINHA que dê a sensação de disponível "
                "agora. É oferta de produto, não aula sobre a origem da "
                "estampa. Diga isso do jeito que couber neste tema — evite as "
                "muletas 'sem fila', 'sem espera' e 'sem estoque', que viram "
                "assinatura repetida entre posts; "
                "(3) uma pergunta direta ao leitor sobre a escolha dele, que dê "
                "motivo para comentar. "
                "Sem emoji. Sem repetir palavra do gancho. Nada de história "
                "cultural do padrão: quem lê quer a capinha, não o contexto."
            ),
        },
        "cta": {
            "type": "string",
            "description": (
                "Chamada para ação em português, até 30 caracteres. Use o "
                "imperativo na 3ª pessoa, que é a forma correta ao tratar o "
                "leitor por 'você': 'Monte a sua', 'Escolha a sua', 'Peça a "
                "sua'. Nunca a 2ª pessoa ('Monta', 'Escolhe', 'Pede')."
            ),
        },
        "hashtags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "De 4 a 6 hashtags em português, sem o caractere '#'.",
        },
        "movimento": {
            "type": "string",
            "description": (
                "Prompt em inglês descrevendo o MOVIMENTO de câmera do vídeo "
                "sobre o mockup já pronto. Não descreve o produto nem a arte."
            ),
        },
    },
    "required": ["conceito_arte", "gancho", "legenda", "cta", "hashtags", "movimento"],
    "additionalProperties": False,
}


class ErroCriativo(RuntimeError):
    """Falha tratada da geração criativa."""


def _sistema(marca: dict[str, Any]) -> str:
    proibido = "\n".join(f"- {item}" for item in marca.get("proibido", []))
    return (
        f"Você é redator publicitário da {marca.get('nome', 'marca')}, varejo "
        "digital brasileiro que fabrica produtos personalizados sob demanda.\n\n"
        f"Voz da marca: {marca.get('voz', '')}\n\n"
        "A vantagem da marca é não ter estoque: uma tendência que surge hoje "
        "pode estar impressa num produto hoje. O conteúdo deve refletir "
        "velocidade e personalização, não catálogo genérico.\n\n"
        f"Proibido, sem exceção:\n{proibido}\n\n"
        "Escreva para TikTok: direto, sem rodeio, sem linguagem corporativa.\n\n"
        "Como o feed funciona, e o que isso exige do texto:\n"
        "- O gancho disputa com o polegar. Ele não descreve o que já está na "
        "tela; ele dá um motivo para ficar.\n"
        "- Da legenda, só a primeira linha aparece antes do 'ver mais'. Se ela "
        "não segurar sozinha, o resto não é lido.\n"
        "- Comentário pesa mais que curtida na distribuição, então a legenda "
        "termina em pergunta respondível — não em 'o que você acha?', que é "
        "pergunta vazia, mas em algo específico daquela estampa.\n"
        "- Escreva como quem manda mensagem, não como quem anuncia. Frases "
        "curtas. Nada de 'descubra', 'confira', 'imperdível'.\n"
        "- O produto é uma capinha, comprada por gente de 16 a 30 anos que a "
        "carrega o dia inteiro. O texto oferece a capinha; não explica de onde "
        "o padrão veio nem dá aula de história do design. Curiosidade sobre a "
        "origem da estampa não vende capinha.\n\n"
        "Português do Brasil correto. Ao dar uma ordem ou convite ao leitor, "
        "use o imperativo na 3ª pessoa — 'Monte a sua', não 'Monta a sua'."
    )


def _usuario(sinal: dict[str, Any], produto: dict[str, Any]) -> str:
    return (
        f"Tendência: {sinal.get('tema')}\n"
        f"Público: {sinal.get('publico')}\n"
        f"Produto: {produto.get('nome')} (linha {produto.get('linha')}, "
        f"SKU {produto.get('sku')})\n\n"
        "Crie o conceito da arte que vai impressa neste produto e o texto do "
        "post. A arte precisa ser imprimível: composição gráfica, sem texto e "
        "sem logotipo."
    )


def gerar(
    *,
    sinal: dict[str, Any],
    produto: dict[str, Any],
    marca: dict[str, Any],
    api_key: str,
    modelo: str = "claude-opus-4-8",
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """Produz o pacote criativo, validado contra os guardrails da marca."""
    cliente = anthropic.Anthropic(api_key=api_key)

    try:
        resposta = cliente.messages.create(
            model=modelo,
            max_tokens=max_tokens,
            system=_sistema(marca),
            messages=[{"role": "user", "content": _usuario(sinal, produto)}],
            output_config={"format": {"type": "json_schema", "schema": ESQUEMA}},
        )
    except anthropic.AuthenticationError as erro:
        raise ErroCriativo("ANTHROPIC_API_KEY inválida ou ausente.") from erro
    except anthropic.RateLimitError as erro:
        raise ErroCriativo("Limite de uso da Anthropic atingido.") from erro
    except anthropic.APIError as erro:
        raise ErroCriativo(f"Falha na chamada à Anthropic: {erro}") from erro

    if resposta.stop_reason == "refusal":
        raise ErroCriativo("A IA recusou gerar este conteúdo. Troque o sinal de tendência.")
    if resposta.stop_reason == "max_tokens":
        raise ErroCriativo(
            f"Resposta truncada em {max_tokens} tokens. Aumente ia.max_tokens no config."
        )

    texto = next((b.text for b in resposta.content if b.type == "text"), None)
    if not texto:
        raise ErroCriativo("Resposta da IA sem conteúdo de texto.")

    try:
        criativo = json.loads(texto)
    except json.JSONDecodeError as erro:  # não deveria ocorrer com schema imposto
        raise ErroCriativo(f"JSON inválido vindo da IA: {erro}") from erro

    violacoes = verificar_guardrails(criativo, marca)
    if violacoes:
        raise ErroCriativo(
            "Conteúdo gerado viola regras da marca: " + "; ".join(violacoes)
        )

    criativo["hashtags"] = _limpar_hashtags(criativo.get("hashtags", []))
    criativo["_uso"] = {
        "tokens_entrada": resposta.usage.input_tokens,
        "tokens_saida": resposta.usage.output_tokens,
    }
    log.info(
        "Criativo gerado (%d tokens de saída): %s",
        resposta.usage.output_tokens,
        criativo.get("gancho"),
    )
    return criativo


def verificar_guardrails(criativo: dict[str, Any], marca: dict[str, Any]) -> list[str]:
    """Confere o texto voltado ao público contra as proibições da marca."""
    visivel = " ".join(
        str(criativo.get(campo, ""))
        for campo in ("gancho", "legenda", "cta")
    )
    visivel += " " + " ".join(str(h) for h in criativo.get("hashtags", []))
    alvo = _normalizar(visivel)

    encontradas: list[str] = []
    for regra in marca.get("proibido", []):
        padrao = PADROES_PROIBIDOS.get(regra)
        if padrao and re.search(padrao, alvo, flags=re.IGNORECASE):
            encontradas.append(regra)
    return encontradas


def _limpar_hashtags(hashtags: list[Any]) -> list[str]:
    limpas: list[str] = []
    for item in hashtags:
        tag = re.sub(r"[^0-9A-Za-zÀ-ÿ]", "", str(item))
        if tag and tag.lower() not in {t.lower() for t in limpas}:
            limpas.append(tag)
    return limpas[:6]


def montar_legenda(criativo: dict[str, Any]) -> str:
    """Junta legenda e hashtags no limite de 2200 caracteres da TikTok."""
    tags = " ".join(f"#{t}" for t in criativo.get("hashtags", []))
    texto = f"{criativo.get('legenda', '').strip()}\n\n{tags}".strip()
    return texto[:2200]
