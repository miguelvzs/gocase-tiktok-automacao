"""O fluxo completo, em uma função só.

`executar_pipeline` é a fonte única de verdade: a API HTTP, o terminal e os
testes chamam esta função, nenhum deles reimplementa etapas. Mesmo contrato do
Desafio 1.

Estágios, espelhando o esqueleto do vídeo de referência:

    sinal + produto      ← "Google Sheets trigger" / "grab the latest media"
    conceito e copy      ← "AI node to create Social Media posts"
    arte → mockup → vídeo  [novo: o vídeo de referência só publicava texto]
    publicação no TikTok ← lugar do "LinkedIn Node"
    relatório            ← "second AI Agent for gmail and slack"
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from . import arte, criativo, mockup, tendencia, video
from .config import carregar, modo_rascunho, segredo
from .publicador import ErroPublicacao, Publicador

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent


def executar_pipeline(
    *,
    sinal_id: str | None = None,
    sku: str | None = None,
    rascunho: bool | None = None,
    saida: Path | None = None,
    progresso: Callable[[str, str], None] | None = None,
    config_caminho: str | Path | None = None,
) -> dict[str, Any]:
    """Executa do sinal de tendência até o post publicado.

    `progresso(etapa, mensagem)` é chamado a cada estágio — a superfície HTTP
    usa isso para relatar o andamento do job sem acoplar-se ao pipeline.
    """
    inicio = time.monotonic()
    cfg = carregar(config_caminho)
    rascunho = modo_rascunho() if rascunho is None else rascunho
    destino = Path(saida) if saida else RAIZ / "output"
    destino.mkdir(parents=True, exist_ok=True)

    def avisar(etapa: str, mensagem: str) -> None:
        log.info("[%s] %s", etapa, mensagem)
        if progresso:
            progresso(etapa, mensagem)

    relatorio: dict[str, Any] = {"rascunho": rascunho, "etapas": {}}

    # 1. Sinal de tendência + produto do catálogo
    avisar("sinal", "Selecionando tendência e produto")
    escolha = tendencia.selecionar(cfg, sinal_id=sinal_id, sku=sku)
    relatorio["sinal"] = escolha["sinal"]
    relatorio["produto"] = escolha["produto"]

    # 2. Conceito de arte, copy e hashtags
    avisar("criativo", f"Redigindo para '{escolha['sinal']['tema']}'")
    pacote = criativo.gerar(
        sinal=escolha["sinal"],
        produto=escolha["produto"],
        marca=cfg["marca"],
        api_key=segredo("ANTHROPIC_API_KEY", obrigatorio=True),  # type: ignore[arg-type]
        modelo=cfg["ia"]["modelo_texto"],
        max_tokens=cfg["ia"]["max_tokens"],
    )
    relatorio["criativo"] = {
        chave: valor for chave, valor in pacote.items() if not chave.startswith("_")
    }
    relatorio["uso_ia"] = pacote.get("_uso", {})

    google_key = segredo("GOOGLE_API_KEY")

    # 3. A arte imprimível — o ativo com valor de negócio
    avisar("arte", "Gerando a arte da capinha")
    area = escolha["produto"].get("area_arte", [1024, 1024])
    caminho_arte, origem_arte = arte.gerar(
        conceito=pacote["conceito_arte"],
        destino=destino / "arte.png",
        paleta=cfg["marca"]["paleta"],
        modelo=cfg["ia"]["modelo_imagem"],
        api_key=google_key,
        tamanho=(int(area[0]), int(area[1])),
    )
    relatorio["etapas"]["arte"] = origem_arte

    # 4. Composição no produto — garante fidelidade que IA de vídeo não dá
    avisar("mockup", "Compondo a arte no produto")
    v = cfg["video"]
    caminho_mockup = mockup.compor(
        arte=caminho_arte,
        destino=destino / "mockup.png",
        paleta=cfg["marca"]["paleta"],
        largura=v["largura"],
        altura=v["altura"],
    )

    # 5. Vídeo 9:16 na especificação da TikTok
    avisar("video", "Montando o vídeo vertical")
    caminho_video, origem_video = video.montar(
        mockup=caminho_mockup,
        destino=destino / "post.mp4",
        gancho=pacote["gancho"],
        cta=pacote["cta"],
        produto=escolha["produto"]["nome"],
        paleta=cfg["marca"]["paleta"],
        largura=v["largura"],
        altura=v["altura"],
        fps=v["fps"],
        duracao=v["duracao_segundos"],
        zoom=v["fallback_zoom"],
        modelo=cfg["ia"]["modelo_video"],
        api_key=google_key,
        prompt_movimento=pacote.get("movimento", ""),
    )
    relatorio["etapas"]["video"] = origem_video
    relatorio["arquivos"] = {
        "arte": str(caminho_arte),
        "mockup": str(caminho_mockup),
        "video": str(caminho_video),
    }
    relatorio["video_mb"] = round(caminho_video.stat().st_size / 1024 / 1024, 2)

    # 6. Publicação
    p = cfg["publicacao"]
    legenda = criativo.montar_legenda(pacote)
    relatorio["legenda_publicada"] = legenda

    with Publicador(segredo("ZERNIO_API_KEY", obrigatorio=True)) as publicador:  # type: ignore[arg-type]
        conta = publicador.conta_tiktok(segredo("ZERNIO_TIKTOK_ACCOUNT_ID"))
        relatorio["conta_tiktok"] = conta

        avisar("upload", "Enviando a mídia")
        url_video = publicador.subir_midia(caminho_video)
        relatorio["url_midia"] = url_video

        avisar("publicacao", "Rascunho no TikTok" if rascunho else "Publicando no TikTok")
        criado = publicador.publicar(
            account_id=conta,
            legenda=legenda,
            url_video=url_video,
            privacidade=p["privacidade_desejada"],
            permitir_comentario=p["permitir_comentario"],
            permitir_duet=p["permitir_duet"],
            permitir_stitch=p["permitir_stitch"],
            feito_com_ia=p["feito_com_ia"],
            tipo_conteudo_comercial=p["tipo_conteudo_comercial"],
            rascunho=rascunho,
        )
        relatorio["post_id"] = criado["post_id"]
        relatorio["url_publica"] = criado["url_publica"]

        if not rascunho and criado["post_id"]:
            avisar("status", "Aguardando confirmação da TikTok")
            try:
                final = publicador.aguardar_publicacao(
                    criado["post_id"],
                    tentativas=p["tentativas_status"],
                    intervalo=p["intervalo_status_segundos"],
                )
                relatorio["estado"] = final["estado"]
                relatorio["url_publica"] = final["url_publica"] or criado["url_publica"]
            except ErroPublicacao as erro:
                # O post existe; só o desfecho é desconhecido. Não republicar.
                relatorio["estado"] = "indeterminado"
                relatorio["aviso"] = str(erro)
        else:
            relatorio["estado"] = "rascunho" if rascunho else "criado"

    relatorio["segundos"] = round(time.monotonic() - inicio, 1)
    avisar("fim", _resumo(relatorio))
    return relatorio


def _resumo(relatorio: dict[str, Any]) -> str:
    """Relatório final legível — o equivalente ao 2º AI Agent do vídeo."""
    partes = [
        f"{relatorio['produto']['nome']} · {relatorio['sinal']['tema']}",
        f"estado={relatorio.get('estado')}",
        f"arte={relatorio['etapas'].get('arte')}",
        f"video={relatorio['etapas'].get('video')}",
        f"{relatorio.get('video_mb')} MB",
        f"{relatorio.get('segundos')}s",
    ]
    if relatorio.get("url_publica"):
        partes.append(str(relatorio["url_publica"]))
    return " | ".join(partes)
