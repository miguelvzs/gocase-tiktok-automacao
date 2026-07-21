"""Geração da arte que vai impressa na capinha.

Este é o ativo com valor de negócio do projeto. Um clipe de vídeo generativo
não é imprimível; uma arte é. A GoCase fabrica sob demanda, então o que a
automação precisa produzir é um arquivo que a fábrica conseguiria usar.

Três caminhos, mesma assinatura, em ordem de preferência:

  1. **Gerador de imagem** (Nano Banana) — maior alcance visual: textura,
     pintura, grão. É o melhor resultado quando há cota disponível.
  2. **Vetor desenhado pelo Claude** — SVG rasterizado localmente. Perde
     textura, mas acerta o tema, e vetor é o formato certo para impressão:
     escala sem perda e separa cores.
  3. **Composição geométrica local** — sempre disponível, na paleta da marca.

Os caminhos de reserva não são decoração. Cota acaba, chave falta, API muda. A
resposta sempre informa qual foi usado, no campo `etapas.arte` do relatório.

A rasterização usa svglib e reportlab (Python puro) e pypdfium2 (binário
embutido no pacote). Nenhuma dependência de biblioteca do sistema — a mesma
escolha feita para o FFmpeg, pelo mesmo motivo: o projeto precisa subir num
runtime onde não existe apt-get.
"""

from __future__ import annotations

import base64
import colorsys
import hashlib
import logging
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter

log = logging.getLogger(__name__)

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"


def motivo_http(erro: Exception) -> str:
    """Extrai a mensagem real de um erro HTTP.

    Sem isto, a falha vira "400 Bad Request" — que não diz se o problema foi
    formato de requisição, cota ou credencial, e transforma diagnóstico em
    adivinhação.
    """
    resposta = getattr(erro, "response", None)
    if resposta is None:
        return str(erro)
    try:
        corpo = resposta.json().get("error", {})
        detalhe = corpo.get("message") or corpo.get("status") or resposta.text
    except Exception:
        detalhe = resposta.text
    return f"HTTP {resposta.status_code}: {str(detalhe)[:300]}"


def gerar(
    *,
    conceito: str,
    destino: Path,
    paleta: dict[str, str],
    modelo: str,
    api_key: str | None,
    tamanho: tuple[int, int] = (1024, 1024),
    chave_anthropic: str | None = None,
    modelo_texto: str = "claude-opus-4-8",
) -> tuple[Path, str]:
    """Produz a arte.

    Devolve `(caminho, origem)` com origem em `imagem_ia`, `vetor_ia` ou
    `local`, na ordem de preferência descrita no topo do módulo.
    """
    if api_key:
        try:
            _gerar_com_ia(
                conceito=conceito,
                destino=destino,
                modelo=modelo,
                api_key=api_key,
                tamanho=tamanho,
            )
            log.info("Arte gerada por IA de imagem: %s", destino.name)
            return destino, "imagem_ia"
        except Exception as erro:
            log.warning(
                "Geração de arte por IA de imagem falhou (%s); tentando vetor.",
                motivo_http(erro),
            )

    if chave_anthropic:
        try:
            _gerar_vetor(
                conceito=conceito,
                destino=destino,
                api_key=chave_anthropic,
                modelo=modelo_texto,
                tamanho=tamanho,
            )
            log.info("Arte vetorial gerada e rasterizada: %s", destino.name)
            return destino, "vetor_ia"
        except Exception as erro:
            log.warning(
                "Geração vetorial falhou (%s); usando composição local.", erro
            )

    _gerar_local(conceito=conceito, destino=destino, paleta=paleta, tamanho=tamanho)
    return destino, "local"


# --------------------------------------------------------------------- via IA

# Proporções aceitas pela API de imagem. Pedir um valor fora da lista é erro,
# então escolhemos a mais próxima da área de impressão do produto.
PROPORCOES = {"1:1": 1.0, "3:4": 0.75, "9:16": 0.5625, "4:3": 1.333, "16:9": 1.777}


def _proporcao_proxima(tamanho: tuple[int, int]) -> str:
    alvo = tamanho[0] / tamanho[1]
    return min(PROPORCOES, key=lambda p: abs(PROPORCOES[p] - alvo))


def _gerar_com_ia(
    *,
    conceito: str,
    destino: Path,
    modelo: str,
    api_key: str,
    tamanho: tuple[int, int],
) -> None:
    corpo = {
        "model": modelo,
        "input": [{"type": "text", "text": conceito}],
        "response_format": {
            "type": "image",
            # A API só aceita image/jpeg aqui. Convertemos para PNG ao
            # normalizar, logo abaixo — a arte segue adiante sem perda extra.
            "mime_type": "image/jpeg",
            # Proporção da área de impressão do produto, não do vídeo. A API
            # aceita um conjunto fixo de valores; escolhemos o mais próximo.
            "aspect_ratio": _proporcao_proxima(tamanho),
            "image_size": "1K",
        },
    }
    resposta = httpx.post(
        ENDPOINT,
        json=corpo,
        headers={"x-goog-api-key": api_key},
        timeout=120.0,
    )
    resposta.raise_for_status()
    dados = resposta.json()

    bruto = _extrair_imagem(dados)
    if not bruto:
        raise RuntimeError("resposta da API não trouxe imagem")

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(base64.b64decode(bruto))

    # Normaliza para o tamanho da área de arte do produto.
    with Image.open(destino) as imagem:
        imagem.convert("RGB").resize(tamanho, Image.LANCZOS).save(destino, "PNG")


def _extrair_imagem(dados: dict) -> str | None:
    """Localiza o base64 da imagem tolerando variações do formato de resposta."""
    saida = dados.get("output_image")
    if isinstance(saida, dict) and saida.get("data"):
        return str(saida["data"])
    if isinstance(saida, str):
        return saida
    for item in dados.get("output", []) or []:
        if isinstance(item, dict):
            if item.get("data"):
                return str(item["data"])
            interno = item.get("image") or item.get("inlineData") or {}
            if isinstance(interno, dict) and interno.get("data"):
                return str(interno["data"])
    return None


# ------------------------------------------------------------- vetor por IA

def _esquema_svg(largura: int, altura: int) -> dict:
    return {
        "type": "object",
        "properties": {
            # Vem antes do SVG de propósito. O modelo escreve a ideia primeiro e
            # desenha depois, com a decisão já tomada — em vez de improvisar a
            # composição forma a forma. Custa algumas centenas de tokens e
            # nenhuma ida extra à rede.
            "conceito": {
                "type": "string",
                "description": (
                    "Antes de desenhar, descreva em uma ou duas frases a ideia "
                    "visual: qual é o elemento principal, onde ele fica no eixo "
                    "vertical, o que ocupa o resto do quadro e quais são as três "
                    "ou quatro cores escolhidas para este tema, em hexadecimal."
                ),
            },
            "svg": {
                "type": "string",
                "description": (
                    "Um documento SVG completo e válido, começando em '<svg' e "
                    f"terminando em '</svg>', com viewBox='0 0 {largura} {altura}'. "
                    "Sem texto, sem fontes, sem imagens externas, sem script. "
                    "Apenas formas vetoriais: path, circle, ellipse, rect, "
                    "polygon, polyline, line, g, linearGradient e "
                    "radialGradient. Atributos de acabamento permitidos: "
                    "fill-opacity, stroke-opacity, stroke-width, "
                    "stroke-linecap, stroke-dasharray e transform."
                ),
            }
        },
        "required": ["conceito", "svg"],
        "additionalProperties": False,
    }

# Elementos que nunca devem aparecer numa arte gerada, por dois motivos
# distintos.
#
# Segurança: `image` e href externo fariam o rasterizador buscar recurso remoto;
# `script`, `foreignObject`, `use` e `iframe` são superfície de execução.
#
# Silêncio: `clipPath` e `pattern` são pior que proibidos — o rasterizador os
# ignora sem erro. Um recorte que some deixa o retângulo cobrindo a arte
# inteira, e o resultado é uma peça errada entregue como se estivesse certa.
# Medido: ambos produzem uma única cor chapada. Recusar em voz alta é melhor do
# que aceitar em silêncio e publicar o defeito.
TAGS_PROIBIDAS = {
    "script",
    "image",
    "foreignobject",
    "iframe",
    "clippath",
    "pattern",
    "filter",
    "mask",
}

# `use` sai da lista de proibidos e ganha regra própria.
#
# Ele estava banido junto com os que buscam recurso externo, mas é o elemento
# certo para repetir uma forma — e repetição é como vetor ganha textura. Sem
# ele, pedir um campo de duzentos pontos custa duzentas declarações completas;
# com ele, custa uma definição e duzentas referências curtas.
#
# O risco real não é o elemento, é o destino: `use` apontando para fora
# buscaria recurso remoto. Então a referência precisa ser local, começando em
# '#'. Conferido que o rasterizador desenha `use` idêntico ao inline.
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def _gerar_vetor(
    *,
    conceito: str,
    destino: Path,
    api_key: str,
    modelo: str,
    tamanho: tuple[int, int],
) -> None:
    """Desenha a arte em vetor.

    Não recebe paleta: as cores saem do tema, não da marca. Ver o bloco PALETA
    no prompt do sistema.
    """
    import anthropic

    largura, altura = tamanho
    sistema = (
        "Você é ilustrador vetorial. Produz arte para impressão na traseira de "
        "uma capinha de celular — o produto que o cliente compra e carrega.\n\n"
        f"FORMATO: retrato alto, {largura}x{altura} (proporção "
        f"{largura / altura:.2f}:1). Componha para essa altura — distribua os "
        "elementos ao longo do eixo vertical em vez de concentrá-los no centro. "
        "A composição preenche a tela inteira, sem margem vazia.\n\n"
        # A paleta sai do TEMA, não da marca. Antes o prompt impunha as quatro
        # cores da GoCase a toda arte, e o resultado era que capinha botânica,
        # gamer neon e festa junina saíam todas em laranja e azul-marinho. A
        # identidade da marca pertence ao vídeo — texto, logotipo, chamada —,
        # não ao produto: quem compra uma capinha botânica quer verde.
        "PALETA: escolha de três a cinco cores que pertençam ao próprio tema, "
        "não a uma marca. Uma tendência botânica pede verdes e terrosos; uma "
        "gamer pede neon sobre escuro; uma junina pede fogo sobre noite. "
        "Declare as cores no campo 'conceito' antes de desenhar e depois use "
        "apenas elas e tons derivados. Uma cor deve dominar, outra contrastar "
        "com força e as demais apoiar — evite quatro cores com o mesmo peso.\n\n"
        "DIREÇÃO DE ARTE — o que separa ilustração de clipart:\n"
        "- Um ponto focal claro, ocupando entre um terço e metade da altura. "
        "Os demais elementos são coadjuvantes e menores.\n"
        "- Escala variada: elementos grandes ao fundo, pequenos à frente. "
        "Repetir a mesma forma no mesmo tamanho é o que faz parecer adesivo.\n"
        "- Profundidade por camadas: um plano de fundo, um intermediário e um "
        "primeiro plano, com sobreposição real entre eles.\n"
        "- Gradiente onde há volume ou luz, chapado onde há recorte. Não "
        "aplique gradiente em tudo nem em nada.\n"
        "- Assimetria. Centralizar tudo no eixo é a saída mais previsível.\n"
        "- Densidade desigual: uma região respira, outra concentra detalhe.\n\n"
        # Sem um piso explícito o modelo entrega vinte formas grandes e a peça
        # fica pobre de perto. Textura em vetor não existe como recurso: ela é
        # construída por repetição de elementos pequenos, e isso precisa ser
        # pedido, porque custa formas.
        "DENSIDADE — a peça é impressa e olhada de perto:\n"
        f"- No mínimo 60 elementos. Uma composição com {largura}x{altura} pixels "
        "e vinte formas grandes fica vazia.\n"
        "- Construa textura por repetição: campos de pontos com tamanho e "
        "opacidade variando, hachuras de linhas finas, lascas espalhadas, "
        "granulado de círculos minúsculos. É assim que vetor ganha superfície.\n"
        "- Detalhe interno nas formas principais: uma folha tem nervura, um "
        "planeta tem faixa, uma onda tem espuma. Silhueta sozinha é ícone.\n"
        "- Acabamento nas bordas do quadro: elementos cortados pela margem "
        "sugerem que a cena continua além da capinha.\n\n"
        f"TÉCNICO: viewBox='0 0 {largura} {altura}'. Um retângulo de fundo "
        "cobrindo tudo. Sem texto, sem fonte, sem imagem externa, sem script.\n"
        "Disponíveis: path, circle, ellipse, rect, polygon, polyline, line, g, "
        "linearGradient, radialGradient, e os atributos fill-opacity, "
        "stroke-opacity, stroke-width, stroke-linecap, stroke-dasharray e "
        "transform. Use transparência para sobrepor planos e radialGradient "
        "para luz e volume.\n"
        "Para campos de textura, defina a forma uma vez em <defs> e repita com "
        "<use href='#id' x='..' y='..'>, variando escala e opacidade pelo "
        "transform. Sai muito mais barato que redeclarar cada elemento, o que "
        "deixa espaço para a densidade pedida acima. A referência precisa "
        "começar com '#': apontar para fora é recusado.\n"
        # Ambos são aceitos pelo interpretador e descartados no desenho, o que
        # produziria uma peça errada sem nenhum erro. Medido, não suposto.
        "NUNCA use clipPath, mask, pattern ou filter: o rasterizador os ignora "
        "em silêncio e a arte sai quebrada.\n\n"
        "O terço superior fica atrás do módulo de câmera — evite detalhe fino "
        "ali. O terço inferior é a área mais visível."
    )
    cliente = anthropic.Anthropic(api_key=api_key)
    resposta = cliente.messages.create(
        model=modelo,
        # Folga generosa: truncar o SVG descarta a peça inteira, e o custo é por
        # token gerado, não por teto declarado. Com o piso de densidade pedido
        # acima, um desenho passa de 10 KB — perto demais do limite anterior.
        max_tokens=20000,
        system=sistema,
        messages=[{"role": "user", "content": f"Desenhe: {conceito}"}],
        # Esforço médio em vez do padrão: mede-se 18 s contra 24 s por desenho,
        # com o mesmo número de elementos. Para arte gráfica a deliberação extra
        # não melhora a composição, só atrasa.
        output_config={
            "format": {"type": "json_schema", "schema": _esquema_svg(largura, altura)},
            "effort": "medium",
        },
    )
    if resposta.stop_reason == "max_tokens":
        raise RuntimeError("SVG truncado — a arte ficaria incompleta")

    texto = next((b.text for b in resposta.content if b.type == "text"), "")
    import json

    pacote = json.loads(texto)
    svg = _sanear_namespace(_sanear_cores(pacote["svg"]))
    _conferir_svg(svg)
    _rasterizar(svg, destino, tamanho)
    log.info("Conceito da arte: %s", pacote.get("conceito", "")[:200])
    log.info(
        "Vetor gerado (%d tokens, %d bytes de SVG).",
        resposta.usage.output_tokens,
        len(svg),
    )


# O modelo produz, de vez em quando, uma cor partida por espaço — "#f5 eee6".
# O rasterizador morre com "invalid literal for int() with base 16: 'f5 eee'",
# mensagem que não menciona cor, e a peça inteira é descartada por causa de um
# caractere.
#
# O reparo trabalha sobre o VALOR COMPLETO do atributo, nunca sobre texto solto.
# Uma primeira versão casava qualquer sequência hexadecimal separada por espaço
# e, em "#ab cdefgh", juntava "ab"+"cdef" num "#abcdef" válido deixando "gh"
# sobrando: transformava uma cor quebrada numa cor ERRADA com aparência de
# certa. Exigir que o valor inteiro vire hexadecimal válido elimina isso — se
# não virar, nada é tocado e a conferência abaixo recusa em voz alta.
_NOMES_DE_COR = "fill|stroke|stop-color|flood-color"
_COR_VALIDA = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_COR_COMO_ATRIBUTO = re.compile(rf'({_NOMES_DE_COR})(\s*=\s*")(#[^"]*)(")')
_COR_COMO_ESTILO = re.compile(rf'({_NOMES_DE_COR})(\s*:\s*)(#[^;"\']*)')

# Usado só para conferir; aceita as duas formas acima.
_ATRIBUTO_DE_COR = re.compile(rf"(?:{_NOMES_DE_COR})\s*[:=]\s*[\"']?\s*(#[^\"';\s>)]*)")


def _sanear_namespace(svg: str) -> str:
    """Declara o namespace do xlink quando o documento usa sem declarar.

    Agora que `use` é permitido, o modelo às vezes escreve `xlink:href` e
    esquece o `xmlns:xlink` na raiz. O interpretador rejeita com "unbound
    prefix" e a peça inteira é perdida por uma declaração ausente. Acrescentar o
    que falta não muda o desenho nem afrouxa nenhuma verificação — a origem do
    `use` continua sendo conferida logo abaixo.
    """
    if "xlink:" not in svg or "xmlns:xlink" in svg:
        return svg
    return re.sub(
        r"<svg\b", '<svg xmlns:xlink="http://www.w3.org/1999/xlink"', svg, count=1
    )


def _sanear_cores(svg: str) -> str:
    """Junta cores hexadecimais que vieram partidas por espaço."""

    def corrigir(achado: re.Match[str]) -> str:
        partes = list(achado.groups())
        junto = re.sub(r"\s+", "", partes[2])
        if not _COR_VALIDA.match(junto):
            return achado.group(0)  # não dá para reparar sem inventar
        partes[2] = junto
        return "".join(partes)

    return _COR_COMO_ESTILO.sub(corrigir, _COR_COMO_ATRIBUTO.sub(corrigir, svg))


def _conferir_svg(svg: str) -> None:
    """Recusa SVG malformado ou com elemento capaz de buscar recurso externo."""
    if "<svg" not in svg:
        raise ValueError("resposta não contém elemento <svg>")
    try:
        raiz = ET.fromstring(svg)
    except ET.ParseError as erro:
        raise ValueError(f"SVG malformado: {erro}") from erro

    for elemento in raiz.iter():
        tag = elemento.tag.split("}")[-1].lower()
        if tag in TAGS_PROIBIDAS:
            raise ValueError(f"SVG contém elemento não permitido: <{tag}>")
        if tag == "use":
            alvo = elemento.get("href") or elemento.get(XLINK_HREF) or ""
            if not alvo.startswith("#"):
                raise ValueError(
                    f"<use> só pode referenciar o próprio documento, não {alvo!r}"
                )
    if re.search(r'(xlink:)?href\s*=\s*["\']\s*(https?:|//|file:)', svg, re.I):
        raise ValueError("SVG referencia recurso externo")

    # Depois do saneamento, uma cor ainda quebrada vira erro legível aqui em vez
    # de estourar lá dentro do rasterizador como um problema de conversão.
    for cor in _ATRIBUTO_DE_COR.findall(svg):
        if not _COR_VALIDA.match(cor):
            raise ValueError(f"SVG traz cor hexadecimal inválida: {cor!r}")


def _rasterizar(svg: str, destino: Path, tamanho: tuple[int, int]) -> None:
    """SVG → PDF → PNG, tudo com pacotes pip, sem biblioteca de sistema."""
    import pypdfium2
    from reportlab.graphics import renderPDF
    from svglib.svglib import svg2rlg

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario_svg = destino.with_suffix(".svg")
    temporario_pdf = destino.with_suffix(".pdf")
    temporario_svg.write_text(svg, encoding="utf-8")

    desenho = svg2rlg(str(temporario_svg))
    if desenho is None:
        raise ValueError("svglib não conseguiu interpretar o SVG")
    renderPDF.drawToFile(desenho, str(temporario_pdf))

    # O documento precisa ser fechado antes de remover o arquivo: no Windows o
    # pypdfium2 mantém o PDF aberto e o unlink falha com WinError 32.
    documento = pypdfium2.PdfDocument(str(temporario_pdf))
    try:
        pagina = documento[0]
        escala = max(tamanho) / max(pagina.get_size())
        imagem = pagina.render(scale=escala).to_pil().convert("RGB")
        imagem.resize(tamanho, Image.LANCZOS).save(destino, "PNG")
    finally:
        documento.close()

    temporario_pdf.unlink(missing_ok=True)
    # O .svg fica: é o ativo vetorial que a fábrica usaria para imprimir.


# ------------------------------------------------------------------- local


def _hex_para_rgb(valor: str) -> tuple[int, int, int]:
    valor = valor.lstrip("#")
    return tuple(int(valor[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _gerar_local(
    *,
    conceito: str,
    destino: Path,
    paleta: dict[str, str],
    tamanho: tuple[int, int],
) -> None:
    """Composição geométrica determinística, derivada do texto do conceito.

    O mesmo conceito sempre produz a mesma arte — útil para reproduzir uma
    execução. Conceitos diferentes produzem artes visivelmente diferentes,
    o que também evita o dedup de conteúdo do Zernio.
    """
    largura, altura = tamanho
    semente = int(hashlib.sha256(conceito.encode("utf-8")).hexdigest()[:8], 16)

    primaria = _hex_para_rgb(paleta.get("primaria", "#FF5A1F"))
    secundaria = _hex_para_rgb(paleta.get("secundaria", "#1A1A2E"))
    destaque = _hex_para_rgb(paleta.get("destaque", "#FFD166"))

    imagem = Image.new("RGB", tamanho, secundaria)
    desenho = ImageDraw.Draw(imagem, "RGBA")

    # Gradiente diagonal entre secundária e primária.
    for y in range(altura):
        fracao = y / max(altura - 1, 1)
        cor = tuple(
            int(secundaria[c] + (primaria[c] - secundaria[c]) * fracao)
            for c in range(3)
        )
        desenho.line([(0, y), (largura, y)], fill=cor)

    # Anéis concêntricos deslocados, com raio derivado da semente.
    centro_x = largura * (0.3 + 0.4 * ((semente >> 3) % 100) / 100)
    centro_y = altura * (0.3 + 0.4 * ((semente >> 7) % 100) / 100)
    for indice in range(7):
        raio = largura * (0.12 + indice * 0.09)
        alfa = max(18, 90 - indice * 11)
        desenho.ellipse(
            [centro_x - raio, centro_y - raio, centro_x + raio, centro_y + raio],
            outline=(*destaque, alfa),
            width=max(3, largura // 150),
        )

    # Leque de raios, ângulo inicial vindo da semente.
    angulo_base = (semente % 360) * math.pi / 180
    for indice in range(12):
        angulo = angulo_base + indice * (math.pi / 6)
        fim_x = centro_x + math.cos(angulo) * largura
        fim_y = centro_y + math.sin(angulo) * altura
        desenho.line(
            [(centro_x, centro_y), (fim_x, fim_y)],
            fill=(*destaque, 26),
            width=max(2, largura // 220),
        )

    # Blocos de cor em harmonia análoga. A rotação de matiz fica em ±0.05 para
    # não sair da identidade da marca — variação livre produzia verde numa
    # paleta laranja.
    h, s, v = colorsys.rgb_to_hsv(*[canal / 255 for canal in primaria])
    lado = largura * 0.13
    margem = largura * 0.06
    passo = (largura - 2 * margem - lado) / 4
    for indice in range(5):
        desvio = (((semente >> (indice * 3)) % 21) - 10) / 200  # -0.05 .. +0.05
        cor = tuple(
            int(canal * 255)
            for canal in colorsys.hsv_to_rgb(
                (h + desvio) % 1.0,
                min(0.95, s * (0.75 + 0.25 * ((semente >> indice) % 3))),
                min(1.0, v * (0.80 + 0.20 * ((semente >> (indice + 1)) % 3))),
            )
        )
        px = margem + passo * indice
        py = altura * (0.58 + 0.06 * ((semente >> (indice + 2)) % 4))
        desenho.rounded_rectangle(
            [px, py, px + lado, py + lado],
            radius=int(lado * 0.28),
            fill=(*cor, 205),
        )

    imagem = imagem.filter(ImageFilter.SMOOTH_MORE)
    destino.parent.mkdir(parents=True, exist_ok=True)
    imagem.save(destino, "PNG")
    log.info("Arte composta localmente: %s", destino.name)
