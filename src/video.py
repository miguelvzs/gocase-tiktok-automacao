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
    "rc-lookahead=10:sync-lookahead=0:ref=1:bframes=0"
)
PRESET = "veryfast"
CRF = "20"

# Uma imagem parada entra com um único quadro em t=0. Um fade programado para o
# fim do vídeo não teria quadros onde acontecer, e o overlay repetiria o quadro
# inicial — com alfa zero, o elemento simplesmente não apareceria.
#
# `-loop 1` na entrada resolve, mas faz o demuxer bufferizar e custa cerca de
# 150 MB por imagem. Repetir o quadro dentro do grafo de filtros tem o mesmo
# efeito por 8 MB: medido em 393,8 MB contra 198,6 MB com duas imagens.
REPETIR_QUADRO = "loop=loop=-1:size=1:start=0"


def _rodar(argumentos: list[str]) -> None:
    processo = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *argumentos],
        capture_output=True,
        text=True,
    )
    if processo.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou: {processo.stderr.strip()[:500]}")


def _para_hex(valor: str) -> str:
    """Cor no formato que o filtro `color` do FFmpeg aceita."""
    return "0x" + valor.lstrip("#")


def _hex_para_rgb(valor: str) -> tuple[int, int, int]:
    valor = valor.lstrip("#")
    return tuple(int(valor[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def montar(
    *,
    mockup: Path,
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
    logo: Path | None = None,
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

    if logo is not None:
        logo = _recortar_margem(logo, trabalho / "logo_recortado.png")

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

    _finalizar(
        base=entrada,
        filtro_base=filtro_base,
        sobreposicao=sobreposicao,
        destino=destino,
        largura=largura,
        altura=altura,
        fps=fps,
        duracao=duracao,
        logo=logo,
        # Véu claro: o logotipo da marca é azul, desenhado para fundo
        # claro. Sobre a cor secundária, escura, o contraste morria.
        cor_veu=paleta.get("fundo", "#F7F7F9"),
    )
    log.info(
        "Vídeo pronto: %s (%.1f MB, origem=%s)",
        destino.name,
        destino.stat().st_size / 1024 / 1024,
        origem,
    )
    return destino, origem


def _recortar_margem(logo: Path, destino: Path) -> Path:
    """Remove a moldura transparente em volta do logotipo.

    Arquivos de marca costumam vir num quadrado com muita margem vazia — o que
    recebemos era 1080x1080 com 96% de transparência. Escalar isso pela largura
    da imagem deixaria o wordmark minúsculo, porque a maior parte da largura é
    vazio. O recorte pela caixa do conteúdo faz a escala valer para a marca, não
    para a moldura.
    """
    with Image.open(logo) as imagem:
        rgba = imagem.convert("RGBA")
        caixa = rgba.getchannel("A").getbbox()
        if caixa is None:
            return logo
        recortado = rgba.crop(caixa)
    destino.parent.mkdir(parents=True, exist_ok=True)
    recortado.save(destino, "PNG")
    log.info(
        "Logotipo recortado de %s para %s.", rgba.size, recortado.size
    )
    return destino


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

def _ken_burns(largura: int, altura: int, fps: int, duracao: int, zoom: float) -> str:
    """Cadeia de filtros do zoom lento sobre o mockup parado.

    Devolve só a expressão: quem codifica é `_finalizar`, num passe único.

    O `zoompan` já multiplica o quadro único de entrada pelo parâmetro `d` — não
    existe `-loop 1` na entrada. O loop fazia o demuxer bufferizar e custava
    ~150 MB a mais para produzir exatamente o mesmo vídeo.

    Não há pré-escalonamento antes do zoom. Ele existia para evitar ampliar
    pixels já renderizados, mas processar 1620x2880 dobra o trabalho por quadro
    — e o serviço codifica com uma thread só, num processador compartilhado, o
    que torna cada pixel caro. Com zoom máximo de 1,18 a perda de nitidez é
    imperceptível sobre arte vetorial, que já é suave.
    """
    quadros = duracao * fps
    passo = (zoom - 1.0) / quadros
    return (
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
    reserva_base: int = 0,
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
    # `reserva_base` é o espaço do logotipo, quando existe: o texto sobe para
    # não disputar a faixa com a assinatura de marca.
    base_y = int(altura * ZONA_SEGURA_BASE) - reserva_base - altura_bloco
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
    logo: Path | None = None,
    cor_veu: str = "#F7F7F9",
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

    # Índices dos inputs são posicionais no FFmpeg, então precisam ser
    # calculados: o logotipo é opcional e a faixa silenciosa só entra quando a
    # origem não tem áudio.
    proximo = 2
    indice_logo = None
    if logo is not None:
        argumentos += ["-i", str(logo)]
        indice_logo = proximo
        proximo += 1
    indice_audio = None
    if not tem_audio:
        argumentos += [
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        ]
        indice_audio = proximo

    if indice_logo is None:
        grafo = f"{filtro_base}[bg][1:v]overlay=0:0:format=auto[v]"
    else:
        # Encerramento de marca. A primeira tentativa colocou o logotipo sobre
        # o produto, no rodapé — e ele lia como se estivesse impresso na
        # capinha, porque o produto ocupa quase toda a altura útil e não sobra
        # faixa livre. Aqui a marca fecha o vídeo.
        #
        # O véu é feito com `fade` para a cor, não com uma fonte de cor
        # sobreposta: a fonte gerava um vídeo RGBA inteiro e exigia um terceiro
        # overlay de tela cheia. Mistura alfa de tela cheia é cara quando se
        # codifica com uma thread só. O texto some junto, sem precisar do
        # próprio fade.
        entrada = max(0.0, duracao - 1.7)
        largura_logo = int(largura * 0.42)
        grafo = (
            f"{filtro_base}"
            f"[bg][1:v]overlay=0:0:format=auto,"
            f"fade=t=out:st={entrada:.2f}:d=0.7:color={_para_hex(cor_veu)}[fechado];"
            f"[{indice_logo}:v]{REPETIR_QUADRO},format=rgba,scale={largura_logo}:-1,"
            f"fade=t=in:st={entrada + 0.3:.2f}:d=0.6:alpha=1[marca];"
            f"[fechado][marca]overlay=(W-w)/2:(H-h)/2:format=auto[v]"
        )

    argumentos += [
        "-filter_complex",
        grafo,
        "-map", "[v]",
        "-map", "0:a?" if tem_audio else f"{indice_audio}:a",
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
