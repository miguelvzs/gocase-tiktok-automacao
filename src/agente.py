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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from . import arte, criativo, mockup, radar, tendencia, video
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

    relatorio: dict[str, Any] = {"rascunho": rascunho, "etapas": {}, "tempos": {}}
    marca_tempo = time.monotonic()

    def cronometrar(nome: str) -> None:
        """Fecha o estágio anterior. Torna o custo mensurável, não presumido."""
        nonlocal marca_tempo
        agora = time.monotonic()
        relatorio["tempos"][nome] = round(agora - marca_tempo, 1)
        marca_tempo = agora

    # 1. Sinal de tendência + produto do catálogo
    #
    # O radar lê o que o Brasil está pesquisando agora e faz a triagem. Ele
    # recusa muito mais do que aprova — política, tragédia, nome de pessoa e
    # clube de futebol dominam as altas, e nada disso vira estampa. Quando não
    # sobra nada, o catálogo curado assume, que é o caminho mais frequente.
    chave_texto = segredo("ANTHROPIC_API_KEY", obrigatorio=True)
    sinais_do_radar: list[dict[str, Any]] = []
    recusados: list[dict[str, str]] = []
    if cfg.get("radar", {}).get("usar_tendencias_reais", False) and not sinal_id:
        avisar("radar", "Lendo tendências reais e filtrando")
        sinais_do_radar, recusados = radar.buscar_sinais(
            api_key=chave_texto,
            modelo=cfg["ia"]["modelo_texto"],
            regiao=cfg.get("radar", {}).get("regiao", "BR"),
        )
        relatorio["radar"] = {
            "aprovados": [s["tema"] for s in sinais_do_radar],
            "recusados": recusados,
        }
        cronometrar("radar")

    avisar("sinal", "Selecionando tendência e produto")
    escolha = tendencia.selecionar(
        cfg, sinal_id=sinal_id, sku=sku, sinais_do_radar=sinais_do_radar
    )
    relatorio["sinal"] = escolha["sinal"]
    relatorio["produto"] = escolha["produto"]
    relatorio["etapas"]["origem_do_tema"] = (
        "radar" if escolha["sinal"].get("origem") == "radar" else "catalogo"
    )

    # A chave é a mesma para imagem e vídeo, mas os custos são muito diferentes:
    # vídeo custa cerca de 30 vezes mais por execução. Por isso cada etapa tem
    # seu próprio interruptor — ligar o billing na Google não deve abrir as duas
    # torneiras de uma vez, sem o operador escolher.
    google_key = segredo("GOOGLE_API_KEY")
    chave_imagem = google_key if cfg["ia"].get("usar_ia_imagem", True) else None
    chave_video = google_key if cfg["ia"].get("usar_ia_video", False) else None
    area = escolha["produto"].get("area_arte", [1024, 1024])

    # 2 e 3. Texto e arte, em paralelo.
    #
    # Medindo os estágios, as duas chamadas à IA somavam 64% do tempo total e
    # eram sequenciais sem precisar ser: a arte esperava o conceito que o
    # redator escrevia. Mas o desenho sai do mesmo insumo — tendência, público e
    # produto —, então o Claude desenha direto do briefing, sem passar pela
    # descrição intermediária em inglês. Uma tradução a menos e uma espera a
    # menos.
    #
    # O conceito escrito continua sendo gerado: é ele que alimenta o gerador de
    # imagem quando há cota, e aparece no relatório da execução.
    avisar("criativo", f"Redigindo e desenhando para '{escolha['sinal']['tema']}'")
    # A estética entra no briefing porque é ela que dá desenho definido. Tema
    # sozinho — "estética retrô" — deixa a escolha visual inteira para o modelo,
    # que resolve pelo caminho mais previsível. Descrever a linguagem visual em
    # termos executáveis é o que separa ilustração de clipart.
    estetica = escolha["sinal"].get("estetica", "")
    briefing = (
        f"{escolha['sinal']['tema']}. Público: {escolha['sinal'].get('publico', '')}. "
        f"Produto: {escolha['produto']['nome']}."
        + (f"\n\nLinguagem visual pedida: {estetica.strip()}" if estetica else "")
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_texto = executor.submit(
            criativo.gerar,
            sinal=escolha["sinal"],
            produto=escolha["produto"],
            marca=cfg["marca"],
            api_key=chave_texto,  # type: ignore[arg-type]
            modelo=cfg["ia"]["modelo_texto"],
            max_tokens=cfg["ia"]["max_tokens"],
        )
        f_arte = executor.submit(
            arte.gerar,
            conceito=briefing,
            destino=destino / "arte.png",
            paleta=cfg["marca"]["paleta"],
            modelo=cfg["ia"]["modelo_imagem"],
            api_key=chave_imagem,
            tamanho=(int(area[0]), int(area[1])),
            chave_anthropic=chave_texto,
            modelo_texto=cfg["ia"]["modelo_texto"],
        )
        # O texto vem primeiro de propósito: se os guardrails de marca barrarem
        # o conteúdo, a exceção sobe antes de gastar tempo com a arte.
        pacote = f_texto.result()
        caminho_arte, origem_arte = f_arte.result()

    relatorio["criativo"] = {
        chave: valor for chave, valor in pacote.items() if not chave.startswith("_")
    }
    relatorio["uso_ia"] = pacote.get("_uso", {})
    relatorio["etapas"]["arte"] = origem_arte
    cronometrar("criativo_e_arte")

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

    cronometrar("mockup")

    # 5. Vídeo 9:16 na especificação da TikTok
    #
    # O logotipo é opcional de propósito: é material de marca de terceiro e o
    # repositório é público, então o arquivo não é versionado. Sem ele o vídeo
    # sai sem assinatura, e o relatório registra qual foi o caso.
    caminho_logo = RAIZ / str(cfg["marca"].get("logo") or "")
    tem_logo = caminho_logo.is_file()
    relatorio["etapas"]["logo"] = "aplicado" if tem_logo else "ausente"
    if not tem_logo:
        log.info("Logotipo não encontrado em %s; vídeo sem assinatura.", caminho_logo)

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
        api_key=chave_video,
        prompt_movimento=pacote.get("movimento", ""),
        logo=caminho_logo if tem_logo else None,
    )
    relatorio["etapas"]["video"] = origem_video
    relatorio["arquivos"] = {
        "arte": str(caminho_arte),
        "mockup": str(caminho_mockup),
        "video": str(caminho_video),
    }
    relatorio["video_mb"] = round(caminho_video.stat().st_size / 1024 / 1024, 2)
    cronometrar("video")

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

        avisar(
            "publicacao",
            "Enviando ao Creator Inbox" if rascunho else "Publicando no TikTok",
        )
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
        relatorio["destino"] = "creator_inbox" if rascunho else "publicado"

        # Confirmamos o status nos dois modos: mesmo o envio ao Creator Inbox
        # atravessa a TikTok inteira e pode falhar. Só o `estado` final diz se
        # a mídia chegou.
        if criado["post_id"]:
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
                # O id permite ao operador consultar o desfecho no painel sem
                # arriscar republicar e duplicar o post.
                relatorio["consultar_post_id"] = criado["post_id"]
        else:
            relatorio["estado"] = "criado"

        # A TikTok frequentemente devolve o link do post vazio mesmo com status
        # `published`. Sem uma alternativa, o operador recebe "publicado" e
        # nenhuma forma de conferir.
        if not relatorio.get("url_publica"):
            relatorio["url_perfil"] = publicador.perfil_url(conta)

    cronometrar("publicacao")
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
