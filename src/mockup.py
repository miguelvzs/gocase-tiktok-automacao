"""Composição da arte sobre a capinha.

É aqui que a fidelidade de produto é garantida. Pedir a um modelo de vídeo
"uma capinha da GoCase com esta arte" devolve um celular genérico com a arte
aproximada e texto ilegível. Compor por código devolve exatamente o produto
que a fábrica imprimiria.

O quadro sai em 1080x1920 — o formato final do TikTok — para servir tanto de
imagem-base da animação por IA quanto de primeiro quadro do fallback local.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

log = logging.getLogger(__name__)


def _hex_para_rgb(valor: str) -> tuple[int, int, int]:
    valor = valor.lstrip("#")
    return tuple(int(valor[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


# Fator de supersampling: a cena é desenhada nesta escala e reduzida com
# LANCZOS no fim.
#
# O Pillow não antialiasa as formas que desenha. Medindo a borda da capinha num
# mockup 1080x1920, a transição era de um pixel — (212,188,180) direto para
# (24,24,43), sem nenhum tom intermediário. Em reta vertical isso não incomoda,
# mas as quinas arredondadas saíam em degraus visíveis.
#
# Desenhar em dobro e reduzir resolve porque a média de quatro pixels vira o
# meio-tom que faltava. Custa 0,35 s a mais em máquina comum, cerca de 1,8 s no
# serviço publicado, contra um orçamento de 64 s — e o pico de memória não sai
# do lugar. Era inviável no teto de 512 MB antigo; com 4 GB, é troco.
SUPERAMOSTRAGEM = 2


def compor(
    *,
    arte: Path,
    destino: Path,
    paleta: dict[str, str],
    largura: int = 1080,
    altura: int = 1920,
) -> Path:
    """Compõe a arte no produto, desenhando em escala dobrada e reduzindo."""
    fator = SUPERAMOSTRAGEM
    quadro = _desenhar(
        arte=arte, paleta=paleta, largura=largura * fator, altura=altura * fator
    )
    if fator != 1:
        quadro = quadro.resize((largura, altura), Image.LANCZOS)

    destino.parent.mkdir(parents=True, exist_ok=True)
    quadro.save(destino, "PNG")
    log.info("Mockup composto: %s (%dx supersampling)", destino.name, fator)
    return destino


def _desenhar(
    *,
    arte: Path,
    paleta: dict[str, str],
    largura: int,
    altura: int,
) -> Image.Image:
    # Os raios de desfoque abaixo foram calibrados para 1080 de largura. Sem
    # esta escala, desenhar em dobro deixaria as sombras com metade da
    # suavidade relativa — a peça sairia diferente, não apenas mais limpa.
    escala = largura / 1080
    fundo = _hex_para_rgb(paleta.get("fundo", "#F7F7F9"))
    escuro = _hex_para_rgb(paleta.get("secundaria", "#1A1A2E"))
    primaria = _hex_para_rgb(paleta.get("primaria", "#FF5A1F"))

    quadro = Image.new("RGB", (largura, altura), fundo)
    pincel = ImageDraw.Draw(quadro)

    # Fundo com vinheta suave: separa o produto do plano sem competir com ele.
    for y in range(altura):
        fracao = abs(y - altura / 2) / (altura / 2)
        cor = tuple(int(fundo[c] * (1 - 0.10 * fracao)) for c in range(3))
        pincel.line([(0, y), (largura, y)], fill=cor)

    # Halo na cor primária atrás do produto.
    halo = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse(
        [largura * 0.08, altura * 0.20, largura * 0.92, altura * 0.80],
        fill=(*primaria, 46),
    )
    quadro = Image.alpha_composite(
        quadro.convert("RGBA"), halo.filter(ImageFilter.GaussianBlur(90 * escala))
    ).convert("RGB")

    # Geometria da capinha: proporção próxima de um smartphone real (~2:1).
    largura_case = int(largura * 0.50)
    altura_case = int(largura_case * 2.03)
    esquerda = (largura - largura_case) // 2
    topo = int(altura * 0.20)
    direita = esquerda + largura_case
    base = topo + altura_case
    raio = int(largura_case * 0.13)

    # Sombra projetada.
    sombra = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle(
        [
            esquerda + 14 * escala,
            topo + 26 * escala,
            direita + 14 * escala,
            base + 26 * escala,
        ],
        radius=raio,
        fill=(0, 0, 0, 105),
    )
    quadro = Image.alpha_composite(
        quadro.convert("RGBA"), sombra.filter(ImageFilter.GaussianBlur(34 * escala))
    ).convert("RGB")

    # Arte recortada na silhueta da capinha.
    with Image.open(arte) as original:
        estampa = original.convert("RGB")
        # Preenche a área sem distorcer: corta o excedente do lado mais longo.
        proporcao = max(largura_case / estampa.width, altura_case / estampa.height)
        estampa = estampa.resize(
            (max(1, int(estampa.width * proporcao)), max(1, int(estampa.height * proporcao))),
            Image.LANCZOS,
        )
        corte_x = (estampa.width - largura_case) // 2
        corte_y = (estampa.height - altura_case) // 2
        estampa = estampa.crop(
            (corte_x, corte_y, corte_x + largura_case, corte_y + altura_case)
        )

    mascara = Image.new("L", (largura_case, altura_case), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        [0, 0, largura_case, altura_case], radius=raio, fill=255
    )
    quadro.paste(estampa, (esquerda, topo), mascara)

    pincel = ImageDraw.Draw(quadro, "RGBA")

    # Borda da capinha.
    pincel.rounded_rectangle(
        [esquerda, topo, direita, base],
        radius=raio,
        outline=(*escuro, 190),
        width=max(3, largura // 300),
    )

    # Módulo de câmera: é o detalhe que faz o objeto ler como capinha de celular
    # e não como retângulo com estampa.
    modulo = int(largura_case * 0.36)
    mx, my = esquerda + int(largura_case * 0.08), topo + int(largura_case * 0.08)
    pincel.rounded_rectangle(
        [mx, my, mx + modulo, my + modulo],
        radius=int(modulo * 0.30),
        fill=(*escuro, 225),
    )
    lente = int(modulo * 0.30)
    for dx, dy in ((0.13, 0.13), (0.53, 0.13), (0.13, 0.53)):
        lx, ly = mx + int(modulo * dx), my + int(modulo * dy)
        pincel.ellipse([lx, ly, lx + lente, ly + lente], fill=(18, 18, 26, 255))
        pincel.ellipse(
            [lx + lente * 0.28, ly + lente * 0.24, lx + lente * 0.52, ly + lente * 0.48],
            fill=(90, 96, 120, 190),
        )

    # Brilho especular diagonal: dá volume ao plástico.
    brilho = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    ImageDraw.Draw(brilho).polygon(
        [
            (esquerda, topo + altura_case * 0.30),
            (direita, topo - altura_case * 0.06),
            (direita, topo + altura_case * 0.13),
            (esquerda, topo + altura_case * 0.50),
        ],
        fill=(255, 255, 255, 34),
    )
    recorte = Image.new("L", (largura, altura), 0)
    ImageDraw.Draw(recorte).rounded_rectangle(
        [esquerda, topo, direita, base], radius=raio, fill=255
    )
    brilho.putalpha(
        Image.composite(brilho.getchannel("A"), Image.new("L", (largura, altura), 0), recorte)
    )
    quadro = Image.alpha_composite(
        quadro.convert("RGBA"), brilho.filter(ImageFilter.GaussianBlur(12 * escala))
    ).convert("RGB")

    return quadro
