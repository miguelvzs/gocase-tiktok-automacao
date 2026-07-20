"""Montagem do vídeo 9:16 para o TikTok.

Estratégia image-to-video, não text-to-video: o mockup já resolveu a fidelidade
do produto, e a IA só precisa dar movimento. Pedir a um modelo de vídeo que
invente a capinha do zero devolve um celular genérico e texto ilegível.

Caminho principal: Veo anima o mockup.
Caminho reserva: FFmpeg aplica Ken Burns sobre o mockup.

Os dois convergem para a mesma finalização em FFmpeg, que é quem garante a
especificação que a TikTok exige — 1080x1920, H.264, yuv420p, 30 fps, faixa de
áudio presente. A legenda em tela é composta em PNG pelo Pillow e sobreposta
como imagem: usar o filtro drawtext exigiria apontar para um arquivo de fonte
do sistema, que é justamente o tipo de caminho de disco que quebra ao mover o
projeto de máquina.
"""

from __future__ import annotations

import base64
import logging
import subprocess
import time
from pathlib import Path

import httpx
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

log = logging.getLogger(__name__)

BASE_GOOGLE = "https://generativelanguage.googleapis.com/v1beta"
DURACOES_VEO = {4, 6, 8}  # a API só aceita estes valores

# A interface da TikTok cobre a base do vídeo com legenda, nome do perfil e
# botões de ação. Texto colocado abaixo desta fração da altura fica escondido
# atrás dela — foi o que aconteceu com o CTA da primeira publicação real, e só
# apareceu ao abrir o post no aplicativo.
ZONA_SEGURA_BASE = 0.76


def _ffmpeg() -> str:
    """Binário estático embarcado pelo pacote. Não depende de instalação."""
    return imageio_ffmpeg.get_ffmpeg_exe()


# Parâmetros de codificação escolhidos por medição, não por hábito.
#
# O libx264 aloca buffers de quadro por thread e por quadro de lookahead. Nos
# padrões, codificar 1080x1920 consumia 906 MB — mais do que o container de
# 512 MB do plano gratuito, e o serviço morria por falta de memória.
#
# `-threads` do FFmpeg NÃO controla o threading interno do x264; é preciso
# passar `threads=1` dentro de `-x264-params`. Só isso derrubou de 906 para
# 336 MB. Limitar refs e lookahead levou a 293.
#
# A quantidade de memória não é problema de qualidade aqui: o arquivo final
# fica abaixo de 1 MB contra um teto de 25 MB, então sobra folga para usar um
# CRF baixo e compensar o preset rápido.
X264_ECONOMICO = (
    "threads=1:lookahead_threads=1:sliced-threads=0:"
    "rc-lookahead=10:sync-lookahead=0:ref=2:bframes=0"
)
PRESET = "veryfast"
CRF = "20"


def _rodar(argumentos: list[str]) -> None:
    processo = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *argumentos],
        capture_output=True,
        text=True,
    )
    if processo.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou: {processo.stderr.strip()[:500]}")


def _hex_para_rgb(valor: str) -> tuple[int, int, int]:
    valor = valor.lstrip("#")
    return tuple(int(valor[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def montar(
    *,
    mockup: Path,
    arte: Path | None = None,
    destino: Path,
    gancho: str,
    cta: str,
    produto: str,
    paleta: dict[str, str],
    largura: int = 1080,
    altura: int = 1920,
    fps: int = 30,
    duracao: int = 8,
    zoom: float = 1.18,
    modelo: str = "veo-3.1-fast-generate-preview",
    api_key: str | None = None,
    prompt_movimento: str = "",
) -> tuple[Path, str]:
    """Produz o MP4 final. Devolve (caminho, origem) com origem 'ia' ou 'local'."""
    trabalho = destino.parent
    trabalho.mkdir(parents=True, exist_ok=True)
    bruto = trabalho / "base.mp4"
    origem = "local"

    if api_key:
        try:
            _animar_com_ia(
                mockup=mockup,
                destino=bruto,
                modelo=modelo,
                api_key=api_key,
                duracao=duracao,
                prompt=prompt_movimento or _prompt_padrao(produto),
            )
            origem = "ia"
        except Exception as erro:
            from .arte import motivo_http

            log.warning(
                "Geração de vídeo por IA falhou (%s); usando animação local.",
                motivo_http(erro),
            )

    # Uma única codificação, não duas. Antes o caminho local gerava um MP4
    # intermediário que era relido e recodificado para receber a legenda —
    # decodificar e codificar 1080x1920 ao mesmo tempo custava 448 MB, acima do
    # que um container de 512 MB suporta. Agora o movimento e a legenda entram
    # no mesmo grafo de filtros e o vídeo é codificado uma vez só.
    if origem == "ia":
        entrada = bruto
        filtro_base = (
            f"[0:v]scale={largura}:{altura}:force_original_aspect_ratio=increase,"
            f"crop={largura}:{altura},fps={fps}[bg];"
        )
    else:
        entrada = mockup
        filtro_base = f"[0:v]{_ken_burns(largura, altura, fps, duracao, zoom)}[bg];"
        log.info("Animação local (Ken Burns, zoom %.2f) no mesmo passe.", zoom)

    sobreposicao = trabalho / "legenda.png"
    _desenhar_legenda(
        destino=sobreposicao,
        gancho=gancho,
        cta=cta,
        produto=produto,
        paleta=paleta,
        largura=largura,
        altura=altura,
    )

    # Vídeo em cenas, quando a arte é vetorial: a estrutura em camadas do SVG
    # permite animar o desenho se montando antes de virar produto. Só vale para
    # o caminho local — vídeo vindo da IA já tem movimento próprio.
    if origem == "local" and arte is not None and arte.with_suffix(".svg").exists():
        try:
            from .arte import rasterizar_camadas

            camadas = rasterizar_camadas(
                arte.with_suffix(".svg"),
                trabalho / "camadas",
                tamanho=(512, 1024),
                passos=10,
            )
            abertura = trabalho / "legenda_abertura.png"
            _desenhar_legenda(
                destino=abertura, gancho=gancho, cta=cta, produto=produto,
                paleta=paleta, largura=largura, altura=altura, com_base=False,
            )
            _animar_cenas(
                camadas=camadas,
                mockup=mockup,
                sobreposicao=sobreposicao,
                sobreposicao_abertura=abertura,
                destino=destino,
                largura=largura,
                altura=altura,
                fps=fps,
                duracao=duracao,
                paleta=paleta,
            )
            log.info(
                "Vídeo pronto: %s (%.1f MB, origem=cenas)",
                destino.name,
                destino.stat().st_size / 1024 / 1024,
            )
            return destino, "cenas"
        except Exception as erro:
            log.warning("Montagem em cenas falhou (%s); usando quadro único.", erro)

    _finalizar(
        base=entrada,
        filtro_base=filtro_base,
        sobreposicao=sobreposicao,
        destino=destino,
        largura=largura,
        altura=altura,
        fps=fps,
        duracao=duracao,
    )
    log.info(
        "Vídeo pronto: %s (%.1f MB, origem=%s)",
        destino.name,
        destino.stat().st_size / 1024 / 1024,
        origem,
    )
    return destino, origem


def _prompt_padrao(produto: str) -> str:
    return (
        f"Slow cinematic product shot of a phone case ({produto}) rotating "
        "gently, subtle parallax, soft studio lighting, shallow depth of field. "
        "Keep the printed artwork on the case exactly as shown, do not redraw "
        "it, do not add text or logos."
    )


# ------------------------------------------------------------------- Veo (IA)


def _animar_com_ia(
    *,
    mockup: Path,
    destino: Path,
    modelo: str,
    api_key: str,
    duracao: int,
    prompt: str,
) -> None:
    if duracao not in DURACOES_VEO:
        duracao = min(DURACOES_VEO, key=lambda opcao: abs(opcao - duracao))
        log.info("Duração ajustada para %ds — valor aceito pelo Veo.", duracao)

    imagem = base64.b64encode(mockup.read_bytes()).decode("ascii")
    cabecalho = {"x-goog-api-key": api_key}

    inicio = httpx.post(
        f"{BASE_GOOGLE}/models/{modelo}:predictLongRunning",
        json={
            "instances": [
                {
                    "prompt": prompt,
                    "image": {"inlineData": {"mimeType": "image/png", "data": imagem}},
                }
            ],
            "parameters": {
                "aspectRatio": "9:16",
                "resolution": "1080p",
                "durationSeconds": duracao,
            },
        },
        headers=cabecalho,
        timeout=120.0,
    )
    inicio.raise_for_status()
    operacao = inicio.json().get("name")
    if not operacao:
        raise RuntimeError("a API não devolveu o nome da operação")

    # Geração leva de 1 a 3 minutos. É por isso que a superfície HTTP deste
    # projeto é assíncrona: nenhum request síncrono sobrevive a essa espera.
    for tentativa in range(60):
        time.sleep(5)
        estado = httpx.get(
            f"{BASE_GOOGLE}/{operacao}", headers=cabecalho, timeout=60.0
        )
        estado.raise_for_status()
        corpo = estado.json()
        if corpo.get("done"):
            if corpo.get("error"):
                raise RuntimeError(str(corpo["error"])[:300])
            uri = _uri_do_video(corpo)
            if not uri:
                raise RuntimeError("operação concluída sem URI de vídeo")
            with httpx.stream(
                "GET", uri, headers=cabecalho, timeout=300.0, follow_redirects=True
            ) as fluxo:
                fluxo.raise_for_status()
                destino.parent.mkdir(parents=True, exist_ok=True)
                with destino.open("wb") as saida:
                    for bloco in fluxo.iter_bytes():
                        saida.write(bloco)
            log.info("Vídeo gerado pelo Veo em %d tentativas de status.", tentativa + 1)
            return

    raise RuntimeError("tempo esgotado aguardando o Veo")


def _uri_do_video(corpo: dict) -> str | None:
    resposta = corpo.get("response", {})
    amostras = (
        resposta.get("generateVideoResponse", {}).get("generatedSamples")
        or resposta.get("generatedSamples")
        or []
    )
    for amostra in amostras:
        video = amostra.get("video") if isinstance(amostra, dict) else None
        if isinstance(video, dict) and video.get("uri"):
            return str(video["uri"])
    return None


# ---------------------------------------------------------------- Ken Burns


def _animar_cenas(
    *,
    camadas: list[Path],
    mockup: Path,
    sobreposicao: Path,
    sobreposicao_abertura: Path,
    destino: Path,
    largura: int,
    altura: int,
    fps: int,
    duracao: int,
    paleta: dict[str, str],
) -> None:
    """Vídeo em cenas, com a arte se montando antes de virar produto.

    Um quadro parado com zoom lento é linguagem de banco de imagens, não de
    TikTok. Como a arte já vem em camadas vetoriais, dá para animar de verdade
    sem IA de vídeo nenhuma:

        0,0 – 2,4 s   arte se monta, elemento por elemento
        2,4 – 3,2 s   transição da arte para o produto
        3,2 – 8,0 s   capinha com aproximação lenta

    Os quadros são gerados aqui e canalizados direto para o FFmpeg como bytes
    crus. Nada vai a disco, e a memória fica em um quadro por vez em vez de uma
    sequência inteira de PNGs.
    """
    total = duracao * fps
    fim_montagem = int(total * 0.30)
    fim_transicao = int(total * 0.40)

    fundo_cor = _hex_para_rgb(paleta.get("fundo", "#F7F7F9"))
    escuro = _hex_para_rgb(paleta.get("secundaria", "#1A1A2E"))

    # A arte é exibida menor que a tela, centralizada, para caber a moldura.
    arte_l = int(largura * 0.62)
    arte_a = int(arte_l * 2)
    quadros_arte = []
    for caminho in camadas:
        with Image.open(caminho) as img:
            quadros_arte.append(img.convert("RGB").resize((arte_l, arte_a), Image.LANCZOS))

    with Image.open(mockup) as img:
        base_mockup = img.convert("RGB").copy()
    with Image.open(sobreposicao) as img:
        legenda = img.convert("RGBA").copy()
    with Image.open(sobreposicao_abertura) as img:
        legenda_abertura = img.convert("RGBA").copy()

    palco = Image.new("RGB", (largura, altura), fundo_cor)
    for y in range(altura):
        fracao = abs(y - altura / 2) / (altura / 2)
        palco.paste(
            tuple(int(fundo_cor[c] * (1 - 0.12 * fracao)) for c in range(3)),
            (0, y, largura, y + 1),
        )

    fundo_cena = _palco_com_sombra(
        palco, (arte_l, arte_a), escuro, largura, altura
    )

    processo = subprocess.Popen(
        [
            _ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{largura}x{altura}", "-r", str(fps), "-i", "-",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-map", "0:v", "-map", "1:a", "-t", str(duracao),
            "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
            "-x264-params", X264_ECONOMICO,
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
            "-c:a", "aac", "-b:a", "128k", "-shortest",
            "-movflags", "+faststart",
            str(destino),
        ],
        stdin=subprocess.PIPE,
    )

    try:
        for n in range(total):
            if n < fim_montagem:
                quadro = _cena_montagem(
                    fundo_cena, quadros_arte, n / fim_montagem, largura, altura
                )
            elif n < fim_transicao:
                avanco = (n - fim_montagem) / max(1, fim_transicao - fim_montagem)
                quadro = Image.blend(
                    _cena_montagem(fundo_cena, quadros_arte, 1.0, largura, altura),
                    base_mockup,
                    avanco,
                )
            else:
                avanco = (n - fim_transicao) / max(1, total - fim_transicao)
                quadro = _aproximar(base_mockup, avanco, largura, altura)

            # Abertura mostra só o gancho: o bloco inferior cairia sobre a
            # arte, que ocupa o centro. Produto e CTA entram junto com a
            # capinha, que é onde fazem sentido.
            camada_texto = legenda if n >= fim_transicao else legenda_abertura
            forca = min(1.0, n / max(1, fps // 2))
            if forca >= 1.0:
                quadro.paste(camada_texto, (0, 0), camada_texto)
            elif forca > 0:
                suave = camada_texto.copy()
                suave.putalpha(
                    camada_texto.getchannel("A").point(lambda v: int(v * forca))
                )
                quadro.paste(suave, (0, 0), suave)

            processo.stdin.write(quadro.tobytes())  # type: ignore[union-attr]
    finally:
        processo.stdin.close()  # type: ignore[union-attr]
        processo.wait()

    if processo.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ao montar as cenas (código {processo.returncode})")
    log.info("Vídeo em cenas montado (%d camadas de arte).", len(camadas))


def _palco_com_sombra(
    palco: Image.Image,
    tamanho_arte: tuple[int, int],
    borda: tuple[int, int, int],
    largura: int,
    altura: int,
) -> Image.Image:
    """Fundo da cena de abertura, com a sombra da arte já embutida.

    A sombra é difusa, não um retângulo sólido deslocado — bloco de cor atrás
    da arte lê como moldura preta, não como profundidade.

    Calculada uma vez e reaproveitada em todos os quadros. O desfoque custava
    58 ms, quase dois terços do tempo de montar um quadro, e era refeito a cada
    um para uma sombra que muda de forma imperceptível ao longo da cena.
    """
    largura_arte, altura_arte = tamanho_arte
    x = (largura - largura_arte) // 2
    y = (altura - altura_arte) // 2

    manta = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    ImageDraw.Draw(manta).rounded_rectangle(
        [x + 8, y + 16, x + largura_arte + 8, y + altura_arte + 16],
        radius=18,
        fill=(*borda, 120),
    )
    return Image.alpha_composite(
        palco.convert("RGBA"), manta.filter(ImageFilter.GaussianBlur(22))
    ).convert("RGB")


def _cena_montagem(
    fundo: Image.Image,
    camadas: list[Image.Image],
    avanco: float,
    largura: int,
    altura: int,
) -> Image.Image:
    """Arte crescendo e ganhando elementos, centralizada no palco."""
    indice = min(len(camadas) - 1, int(avanco * len(camadas)))
    arte = camadas[indice]
    escala = 0.92 + 0.08 * min(1.0, avanco * 1.2)
    largura_arte = max(2, int(arte.width * escala))
    altura_arte = max(2, int(arte.height * escala))

    quadro = fundo.copy()
    quadro.paste(
        arte.resize((largura_arte, altura_arte), Image.BILINEAR),
        ((largura - largura_arte) // 2, (altura - altura_arte) // 2),
    )
    return quadro


def _aproximar(base: Image.Image, avanco: float, largura: int, altura: int) -> Image.Image:
    """Aproximação lenta sobre o produto, equivalente ao Ken Burns."""
    zoom = 1.0 + 0.14 * avanco
    corte_l = int(largura / zoom)
    corte_a = int(altura / zoom)
    x = (largura - corte_l) // 2
    y = (altura - corte_a) // 2
    # BICUBIC e não LANCZOS: numa aproximação lenta sobre arte já suave a
    # diferença é imperceptível, e LANCZOS custava três vezes mais por quadro.
    return base.crop((x, y, x + corte_l, y + corte_a)).resize(
        (largura, altura), Image.BICUBIC
    )


def _ken_burns(largura: int, altura: int, fps: int, duracao: int, zoom: float) -> str:
    """Cadeia de filtros do zoom lento sobre o mockup parado.

    Devolve só a expressão: quem codifica é `_finalizar`, num passe único.

    O `zoompan` já multiplica o quadro único de entrada pelo parâmetro `d` — não
    existe `-loop 1` na entrada. O loop fazia o demuxer bufferizar e custava
    ~150 MB a mais para produzir exatamente o mesmo vídeo.

    O `scale` antes do zoom evita ampliar pixels já renderizados. O fator é 1,5
    porque só precisa cobrir o zoom máximo (1,18) com folga; dobrar a resolução
    quadruplicaria o buffer de quadro sem ganho de nitidez.
    """
    quadros = duracao * fps
    passo = (zoom - 1.0) / quadros
    fator = 1.5
    return (
        f"scale={int(largura * fator)}:{int(altura * fator)},"
        f"zoompan=z='min(zoom+{passo:.6f},{zoom})'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={quadros}:s={largura}x{altura}:fps={fps}"
    )


# ------------------------------------------------------------------- legenda


def _fonte(tamanho: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Fonte escalável sem depender de caminho do sistema operacional."""
    for caminho in (
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ):
        try:
            return ImageFont.truetype(caminho, tamanho)
        except Exception:
            continue
    # Pillow >= 10.1 aceita tamanho no default: portátil em qualquer máquina.
    return ImageFont.load_default(size=tamanho)


def _quebrar(texto: str, fonte, largura_max: int, desenho: ImageDraw.ImageDraw) -> list[str]:
    linhas: list[str] = []
    atual = ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if desenho.textlength(teste, font=fonte) <= largura_max or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _desenhar_legenda(
    *,
    destino: Path,
    gancho: str,
    cta: str,
    produto: str,
    paleta: dict[str, str],
    largura: int,
    altura: int,
    com_base: bool = True,
) -> Path:
    """Camada de texto. `com_base=False` desenha só o gancho, sem produto e CTA.

    A variante sem base existe para a cena de abertura: ali a arte ocupa o
    centro da tela, e o bloco inferior cairia em cima do desenho. O CTA entra
    quando a capinha aparece — que é também onde ele faz sentido.
    """
    primaria = _hex_para_rgb(paleta.get("primaria", "#FF5A1F"))
    camada = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    pincel = ImageDraw.Draw(camada)

    # Faixas escuras no topo e na base: garantem contraste do texto sobre
    # qualquer arte, inclusive as claras. A queda é quadrática e a faixa cobre
    # toda a área de texto — com queda linear e faixa curta, a última linha do
    # gancho caía sobre o produto e sumia.
    fim_topo = int(altura * 0.32)
    for y in range(fim_topo):
        alfa = int(215 * (1 - y / fim_topo) ** 0.75)
        pincel.line([(0, y), (largura, y)], fill=(0, 0, 0, alfa))
    inicio_base = int(altura * 0.58)
    fim_base = int(altura * ZONA_SEGURA_BASE)
    for y in range(inicio_base, altura if com_base else inicio_base):
        # A faixa escurece até a borda da área segura e mantém a intensidade
        # abaixo dela: o texto termina antes, mas o degradê precisa continuar
        # para não formar uma linha visível de corte.
        fracao = min(1.0, (y - inicio_base) / max(1, fim_base - inicio_base))
        pincel.line([(0, y), (largura, y)], fill=(0, 0, 0, int(225 * fracao**0.75)))

    margem = int(largura * 0.08)
    util = largura - 2 * margem

    fonte_gancho = _fonte(74)
    linhas = _quebrar(gancho, fonte_gancho, util, pincel)[:3]
    y = int(altura * 0.055)
    for linha in linhas:
        pincel.text((margem, y), linha, font=fonte_gancho, fill=(255, 255, 255, 255))
        y += 88

    if not com_base:
        destino.parent.mkdir(parents=True, exist_ok=True)
        camada.save(destino, "PNG")
        return destino

    fonte_produto = _fonte(44)
    fonte_cta = _fonte(62)
    # O bloco inferior termina na borda da área segura, calculado de baixo para
    # cima a partir da altura real do texto — assim continua correto se alguém
    # mudar o tamanho da fonte ou o CTA quebrar em duas linhas.
    linhas_cta = _quebrar(cta, fonte_cta, util, pincel)[:2]
    # O +24 cobre a descida dos glifos abaixo da última linha de base: sem ele
    # o bloco encosta no limite e letras como g e q ultrapassam.
    altura_bloco = 66 + len(linhas_cta) * 74 + 24
    base_y = int(altura * ZONA_SEGURA_BASE) - altura_bloco
    pincel.text(
        (margem, base_y), produto, font=fonte_produto, fill=(*primaria, 255)
    )
    for indice, linha in enumerate(linhas_cta):
        pincel.text(
            (margem, base_y + 66 + indice * 74),
            linha,
            font=fonte_cta,
            fill=(255, 255, 255, 255),
        )

    destino.parent.mkdir(parents=True, exist_ok=True)
    camada.save(destino, "PNG")
    return destino


# ---------------------------------------------------------------- finalização


def _finalizar(
    *,
    base: Path,
    filtro_base: str,
    sobreposicao: Path,
    destino: Path,
    largura: int,
    altura: int,
    fps: int,
    duracao: int,
) -> None:
    """Única codificação do pipeline: movimento, legenda e normalização.

    `filtro_base` transforma a entrada — animação Ken Burns sobre a imagem
    parada, ou reenquadramento do vídeo vindo da IA — e deixa o resultado no
    rótulo `[bg]`. A legenda entra por cima no mesmo grafo.

    A faixa de áudio silenciosa existe de propósito: vídeo sem stream de áudio
    é aceito pela API, mas o processamento da TikTok é mais confiável com ela
    presente. Quando o vídeo de origem já tem áudio, ele é preservado.
    """
    tem_audio = _tem_audio(base)
    argumentos = [
        "-i", str(base),
        "-i", str(sobreposicao),
    ]
    if not tem_audio:
        argumentos += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    argumentos += [
        "-filter_complex",
        f"{filtro_base}[bg][1:v]overlay=0:0:format=auto[v]",
        "-map", "[v]",
        "-map", "0:a?" if tem_audio else "2:a",
        "-t", str(duracao),
        "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
        "-x264-params", X264_ECONOMICO,
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "+faststart",
        str(destino),
    ]
    _rodar(argumentos)

    # O upload direto do Zernio recusa acima de 25 MB. Recomprime uma vez em
    # vez de falhar na publicação depois de todo o trabalho de geração.
    if destino.stat().st_size > 24 * 1024 * 1024:
        log.warning("Vídeo acima de 24 MB; recomprimindo.")
        reduzido = destino.with_name(f"{destino.stem}_leve.mp4")
        _rodar(
            [
                "-i", str(destino),
                "-c:v", "libx264", "-preset", PRESET, "-crf", "30",
                "-x264-params", X264_ECONOMICO,
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
                "-movflags", "+faststart",
                str(reduzido),
            ]
        )
        reduzido.replace(destino)


def _tem_audio(arquivo: Path) -> bool:
    processo = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-i", str(arquivo)],
        capture_output=True,
        text=True,
    )
    return "Audio:" in processo.stderr
