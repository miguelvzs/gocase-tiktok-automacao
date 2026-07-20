"""Geração da arte que vai impressa na capinha.

Este é o ativo com valor de negócio do projeto. Um clipe de vídeo generativo
não é imprimível; uma arte é. A GoCase fabrica sob demanda, então o que a
automação precisa produzir é um arquivo que a fábrica conseguiria usar.

Dois caminhos, mesma assinatura:
  1. Nano Banana (Gemini) — arte gerada por IA a partir do conceito.
  2. Pillow — composição geométrica a partir da paleta da marca.

O fallback não é decoração. Cota de IA acaba, chave falta, API muda. O segundo
caminho garante que o pipeline sempre entregue algo publicável, e a resposta
sempre informa qual foi usado.
"""

from __future__ import annotations

import base64
import colorsys
import hashlib
import logging
import math
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter

log = logging.getLogger(__name__)

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"


def gerar(
    *,
    conceito: str,
    destino: Path,
    paleta: dict[str, str],
    modelo: str,
    api_key: str | None,
    tamanho: tuple[int, int] = (1024, 1024),
) -> tuple[Path, str]:
    """Produz a arte. Devolve (caminho, origem) onde origem é 'ia' ou 'local'."""
    if api_key:
        try:
            _gerar_com_ia(
                conceito=conceito,
                destino=destino,
                modelo=modelo,
                api_key=api_key,
                tamanho=tamanho,
            )
            log.info("Arte gerada por IA: %s", destino.name)
            return destino, "ia"
        except Exception as erro:
            log.warning("Geração por IA falhou (%s); usando composição local.", erro)
    else:
        log.info("GOOGLE_API_KEY ausente; usando composição local.")

    _gerar_local(conceito=conceito, destino=destino, paleta=paleta, tamanho=tamanho)
    return destino, "local"


# --------------------------------------------------------------------- via IA


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
            "mime_type": "image/png",
            # Quadrado: a área de impressão da capinha, não o formato do vídeo.
            "aspect_ratio": "1:1",
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
