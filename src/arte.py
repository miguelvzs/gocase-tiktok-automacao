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
                paleta=paleta,
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
            "svg": {
                "type": "string",
                "description": (
                    "Um documento SVG completo e válido, começando em '<svg' e "
                    f"terminando em '</svg>', com viewBox='0 0 {largura} {altura}'. "
                    "Sem texto, sem fontes, sem imagens externas, sem script. "
                    "Apenas formas vetoriais: path, circle, ellipse, rect, "
                    "polygon, line e linearGradient."
                ),
            }
        },
        "required": ["svg"],
        "additionalProperties": False,
    }

# Elementos e atributos que nunca devem aparecer numa arte gerada. `image` e
# href externo fariam o rasterizador buscar recurso remoto; `script` e
# `foreignObject` são superfície de execução. Não confiamos na instrução do
# prompt para isso — verificamos.
TAGS_PROIBIDAS = {"script", "image", "foreignobject", "use", "iframe"}


def _gerar_vetor(
    *,
    conceito: str,
    destino: Path,
    paleta: dict[str, str],
    api_key: str,
    modelo: str,
    tamanho: tuple[int, int],
) -> None:
    import anthropic

    largura, altura = tamanho
    cores = ", ".join(f"{valor}" for valor in paleta.values())
    sistema = (
        "Você é ilustrador vetorial. Produz arte para impressão na traseira de "
        "uma capinha de celular.\n\n"
        f"FORMATO: retrato alto, {largura}x{altura} (proporção "
        f"{largura / altura:.2f}:1). Componha para essa altura — distribua os "
        "elementos ao longo do eixo vertical em vez de concentrá-los no centro. "
        "A composição preenche a tela inteira, sem margem vazia.\n\n"
        f"PALETA — use exclusivamente estas cores e tons derivados delas "
        f"(mais claro, mais escuro, mais transparente): {cores}. "
        "Não introduza nenhum matiz fora desta lista. Nada de verde, azul, "
        "roxo ou rosa se não estiverem acima.\n\n"
        f"TÉCNICO: viewBox='0 0 {largura} {altura}'. Um retângulo de fundo "
        "cobrindo tudo. Sem texto, sem fonte, sem imagem externa, sem script. "
        "Só formas.\n\n"
        "O terço superior fica atrás do módulo de câmera — evite detalhe fino "
        "ali. O terço inferior é a área mais visível."
    )
    cliente = anthropic.Anthropic(api_key=api_key)
    resposta = cliente.messages.create(
        model=modelo,
        max_tokens=8000,
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

    svg = json.loads(texto)["svg"]
    _conferir_svg(svg)
    _rasterizar(svg, destino, tamanho)
    log.info(
        "Vetor gerado (%d tokens, %d bytes de SVG).",
        resposta.usage.output_tokens,
        len(svg),
    )


SVG_NS = "http://www.w3.org/2000/svg"


def camadas_cumulativas(svg: str, passos: int = 10) -> list[str]:
    """Divide o SVG em versões que revelam os elementos progressivamente.

    Devolve `passos` documentos: o primeiro só com o fundo, o último completo.
    É o que permite animar a arte se montando sozinha, sem IA de vídeo — o
    desenho já vem em elementos separados e achatá-lo direto num PNG jogava
    essa estrutura fora.

    Falha aqui não é fatal: quem chama volta para o vídeo de quadro único.
    """
    ET.register_namespace("", SVG_NS)
    raiz = ET.fromstring(svg)
    filhos = list(raiz)
    if len(filhos) < 3:
        raise ValueError("SVG com elementos de menos para animar em camadas")

    # O primeiro elemento costuma ser o retângulo de fundo: fica em todos os
    # passos, senão a arte piscaria sobre transparência.
    fundo, resto = filhos[:1], filhos[1:]
    # No máximo um passo por elemento: pedir mais passos do que há elementos
    # produziria quadros idênticos, e a animação travaria em vez de progredir.
    passos = max(2, min(passos, len(resto)))

    documentos: list[str] = []
    for indice in range(passos):
        fracao = (indice + 1) / passos
        visiveis = fundo + resto[: max(1, round(len(resto) * fracao))]
        copia = ET.Element(raiz.tag, dict(raiz.attrib))
        copia.extend(visiveis)
        documentos.append(ET.tostring(copia, encoding="unicode"))
    return documentos


def rasterizar_camadas(
    svg_caminho: Path, destino_dir: Path, tamanho: tuple[int, int], passos: int = 10
) -> list[Path]:
    """Rasteriza cada passo cumulativo num PNG. Devolve os caminhos em ordem."""
    documentos = camadas_cumulativas(
        svg_caminho.read_text(encoding="utf-8"), passos=passos
    )
    destino_dir.mkdir(parents=True, exist_ok=True)
    saidas: list[Path] = []
    for indice, documento in enumerate(documentos):
        alvo = destino_dir / f"camada_{indice:02d}.png"
        _rasterizar(documento, alvo, tamanho)
        saidas.append(alvo)
    log.info("Arte separada em %d camadas para animação.", len(saidas))
    return saidas


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
    if re.search(r'(xlink:)?href\s*=\s*["\']\s*(https?:|//|file:)', svg, re.I):
        raise ValueError("SVG referencia recurso externo")


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
