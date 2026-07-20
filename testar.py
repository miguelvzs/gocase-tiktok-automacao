"""Verificação de ponta a ponta.

Roda **sem nenhuma credencial**. Toda etapa que dependeria de API externa é
exercitada pelo caminho de fallback, que é código de produção, não simulação.
Assim quem for avaliar consegue executar sem pedir chave a ninguém.

    python testar.py

As chamadas às APIs pagas (Anthropic, Google, Zernio) são cobertas pela
execução real documentada no README, não por estes testes.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

TRABALHO = RAIZ / "output" / "_teste"

_resultados: list[tuple[bool, str, str]] = []


def checar(nome: str, condicao: bool, detalhe: str = "") -> None:
    _resultados.append((condicao, nome, detalhe))
    marca = "OK  " if condicao else "FALHA"
    print(f"  [{marca}] {nome}" + (f" — {detalhe}" if detalhe else ""))


# --------------------------------------------------------------- configuração


def testar_config() -> None:
    print("\nConfiguração")
    from src.config import carregar, modo_rascunho

    cfg = carregar()
    checar(
        "config.yaml carrega com as seções esperadas",
        all(k in cfg for k in ("marca", "produtos", "sinais", "video", "publicacao", "ia")),
    )
    checar(
        "catálogo tem produtos e sinais",
        len(cfg["produtos"]) >= 1 and len(cfg["sinais"]) >= 2,
        f"{len(cfg['produtos'])} produtos, {len(cfg['sinais'])} sinais",
    )

    quebrado = TRABALHO / "quebrado.yaml"
    quebrado.parent.mkdir(parents=True, exist_ok=True)
    quebrado.write_text("isto: [não fecha", encoding="utf-8")
    padrao = carregar(quebrado)
    checar(
        "YAML inválido cai nos padrões embutidos em vez de derrubar",
        padrao["marca"]["nome"] == "GoCase",
    )
    checar("modo rascunho é o padrão seguro", modo_rascunho() is True)


# ------------------------------------------------------------------- seleção


def testar_selecao() -> None:
    print("\nSeleção de tendência")
    from src.config import carregar
    from src import tendencia

    cfg = carregar()

    fixo = tendencia.selecionar(cfg, sinal_id="gamer-neon", sku="CASE-SAM-S24")
    checar(
        "seleção fixada é determinística",
        fixo["sinal"]["id"] == "gamer-neon" and fixo["produto"]["sku"] == "CASE-SAM-S24",
    )

    try:
        tendencia.selecionar(cfg, sinal_id="nao-existe")
        checar("sinal inexistente é recusado com mensagem útil", False)
    except ValueError as erro:
        checar(
            "sinal inexistente é recusado com mensagem útil",
            "Disponíveis" in str(erro),
        )

    chaves = {tendencia.selecionar(cfg)["chave"] for _ in range(8)}
    checar(
        "execuções seguidas variam (evita o dedup de 24h do Zernio)",
        len(chaves) >= 3,
        f"{len(chaves)} combinações distintas em 8 execuções",
    )


# ---------------------------------------------------------------- guardrails


def testar_guardrails() -> None:
    print("\nGuardrails de marca")
    from src.config import carregar
    from src import criativo

    marca = carregar()["marca"]

    limpos = [
        ("O retro dos anos 90 voltou", "Arte nova na sua capinha", "Monte a sua"),
        ("Curadoria de estampas", "Seleção da semana", "Escolha a sua"),
    ]
    passaram = all(
        not criativo.verificar_guardrails(
            {"gancho": g, "legenda": l, "cta": c, "hashtags": []}, marca
        )
        for g, l, c in limpos
    )
    checar("conteúdo legítimo não é barrado", passaram)

    violacoes = {
        "preço": "Capinha por R$ 49",
        "desconto": "30% de desconto hoje",
        "prazo": "Chega em 3 dias úteis",
        "superlativo": "A mais revolucionária capinha",
        "superlativo sintético": "A melhor do mundo",
        "concorrente": "Melhor que as outras marcas",
        "religião": "Uma oração pela sua capinha",
        "política": "A eleição chegou",
    }
    barrados = [
        nome
        for nome, texto in violacoes.items()
        if criativo.verificar_guardrails(
            {"gancho": texto, "legenda": "x", "cta": "y", "hashtags": []}, marca
        )
    ]
    checar(
        "toda violação de marca é barrada",
        len(barrados) == len(violacoes),
        f"{len(barrados)}/{len(violacoes)}",
    )

    legenda = criativo.montar_legenda(
        {"legenda": "A" * 2500, "hashtags": ["retro", "gocase"]}
    )
    checar(
        "legenda respeita o limite de 2200 caracteres da TikTok",
        len(legenda) <= 2200,
        f"{len(legenda)} caracteres",
    )

    tags = criativo._limpar_hashtags(["#retro", "retro", "go case!", "", "a" * 5])
    checar(
        "hashtags são higienizadas e desduplicadas",
        "#" not in "".join(tags) and len(tags) == len(set(t.lower() for t in tags)),
        str(tags),
    )


# --------------------------------------------------------------------- mídia


def testar_midia() -> None:
    print("\nPipeline de mídia (caminho de fallback, sem IA)")
    from PIL import Image

    from src.config import carregar
    from src import arte, mockup, video

    cfg = carregar()
    paleta = cfg["marca"]["paleta"]
    v = cfg["video"]
    TRABALHO.mkdir(parents=True, exist_ok=True)

    conceito = "estética retrô anos 90, formas geométricas"
    caminho, origem = arte.gerar(
        conceito=conceito,
        destino=TRABALHO / "arte.png",
        paleta=paleta,
        modelo="",
        api_key=None,
        tamanho=(1024, 1024),
    )
    with Image.open(caminho) as img:
        tamanho_ok = img.size == (1024, 1024)
    checar("arte é gerada sem chave de IA", origem == "local" and tamanho_ok)

    primeiro = caminho.read_bytes()
    arte.gerar(
        conceito=conceito,
        destino=TRABALHO / "arte2.png",
        paleta=paleta,
        modelo="",
        api_key=None,
        tamanho=(1024, 1024),
    )
    checar(
        "mesmo conceito produz a mesma arte (execução reproduzível)",
        primeiro == (TRABALHO / "arte2.png").read_bytes(),
    )

    caminho_mockup = mockup.compor(
        arte=caminho, destino=TRABALHO / "mockup.png", paleta=paleta
    )
    with Image.open(caminho_mockup) as img:
        checar("mockup sai em 1080x1920", img.size == (1080, 1920), f"{img.size}")

    caminho_video, origem_video = video.montar(
        mockup=caminho_mockup,
        destino=TRABALHO / "post.mp4",
        gancho="O retro dos anos 90 voltou. A capinha também.",
        cta="Monte a sua agora",
        produto="Capinha iPhone 15 Pro",
        paleta=paleta,
        largura=v["largura"],
        altura=v["altura"],
        fps=v["fps"],
        duracao=v["duracao_segundos"],
        zoom=v["fallback_zoom"],
        api_key=None,
    )
    checar("vídeo é gerado sem chave de IA", origem_video == "local" and caminho_video.exists())

    import imageio_ffmpeg

    sonda = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(caminho_video)],
        capture_output=True,
        text=True,
    ).stderr
    checar("vídeo é H.264 yuv420p 1080x1920", "h264" in sonda and "yuv420p" in sonda and "1080x1920" in sonda)
    checar("vídeo tem faixa de áudio", "Audio:" in sonda)

    duracao = re.search(r"Duration: (\d+):(\d+):([\d.]+)", sonda)
    segundos = (
        int(duracao.group(1)) * 3600 + int(duracao.group(2)) * 60 + float(duracao.group(3))
        if duracao
        else 0
    )
    checar(
        "duração está entre os 3s e 10min exigidos pela TikTok",
        3 <= segundos <= 600,
        f"{segundos:.1f}s",
    )

    mb = caminho_video.stat().st_size / 1024 / 1024
    checar("vídeo cabe no limite de 25 MB do upload direto", mb < 25, f"{mb:.2f} MB")

    # Regressão de um defeito encontrado só ao abrir o post publicado no
    # aplicativo: a interface da TikTok cobre a base do vídeo, e o CTA ficava
    # escondido atrás dela.
    import numpy as np

    legenda = video._desenhar_legenda(
        destino=TRABALHO / "legenda_zona.png",
        gancho="Um gancho longo o suficiente para quebrar em mais de uma linha aqui",
        cta="Monte a sua agora",
        produto="Capinha iPhone 15 Pro",
        paleta=paleta,
        largura=v["largura"],
        altura=v["altura"],
    )
    with Image.open(legenda) as camada:
        pixels = np.array(camada.convert("RGBA"))
    # Texto é pixel claro e opaco; a faixa de contraste é escura e não conta.
    eh_texto = (pixels[:, :, 3] > 200) & (pixels[:, :, :3].max(axis=2) > 120)
    linhas = np.where(eh_texto.sum(axis=1) > 20)[0]
    limite = v["altura"] * video.ZONA_SEGURA_BASE
    checar(
        "texto respeita a área coberta pela interface da TikTok",
        len(linhas) > 0 and linhas.max() <= limite,
        f"último pixel em {linhas.max() / v['altura'] * 100:.1f}% (limite {video.ZONA_SEGURA_BASE * 100:.0f}%)",
    )


# ------------------------------------------------------------------ n8n e API


def testar_integracoes() -> None:
    print("\nIntegração n8n")
    caminho = RAIZ / "integracoes" / "radar-tendencia-gocase.json"
    bruto = caminho.read_text(encoding="utf-8")
    fluxo = json.loads(bruto)
    nomes = {n["name"] for n in fluxo["nodes"]}

    destinos_ok = all(
        lig["node"] in nomes
        for conexao in fluxo["connections"].values()
        for saida in conexao["main"]
        for lig in saida
    )
    referencias = set(re.findall(r"\$\('([^']+)'\)", bruto))
    checar(
        "workflow é importável: conexões e referências resolvem",
        destinos_ok and referencias <= nomes,
        f"{len(fluxo['nodes'])} nós",
    )

    suspeitos = [p for p in ("sk_", "sk-ant", "Bearer ", '"credentials"') if p in bruto]
    checar("workflow não carrega credencial embutida", not suspeitos, str(suspeitos))

    caminhos_disco = re.findall(r"[A-Za-z]:\\\\|/home/|/Users/", bruto)
    checar("workflow não carrega caminho de disco fixo", not caminhos_disco)

    print("\nSuperfície HTTP")
    import api

    rotas = {r.path for r in api.app.routes if hasattr(r, "path")}
    checar(
        "rotas esperadas existem",
        {"/", "/publicar", "/jobs/{job_id}", "/catalogo"} <= rotas,
    )

    catalogo = api.catalogo()
    checar(
        "/catalogo devolve o mesmo catálogo do config.yaml",
        len(catalogo["produtos"]) >= 1 and len(catalogo["sinais"]) >= 2,
    )

    saude = api.saude()
    checar("/ responde saudável", saude.get("status") == "ok")

    from fastapi import HTTPException

    try:
        api.consultar("job-que-nao-existe")
        checar("job inexistente devolve 404 legível", False)
    except HTTPException as erro:
        checar(
            "job inexistente devolve 404 legível",
            erro.status_code == 404 and "expiram" in str(erro.detail),
        )


def testar_parsers_do_publicador() -> None:
    """Regressão dos formatos de resposta do Zernio.

    Os dois primeiros casos cobrem bugs reais encontrados na revisão contra a
    documentação. Ambos quebrariam toda publicação e nenhum apareceria em teste
    que não olhasse o formato de resposta.
    """
    print("\nParsers de resposta do Zernio")
    from src.publicador import Publicador

    objetos = Publicador._extrair_privacidades(
        {
            "privacyLevels": [
                {"value": "PUBLIC_TO_EVERYONE", "label": "Todos"},
                {"value": "SELF_ONLY", "label": "Só eu"},
            ]
        }
    )
    checar(
        "privacyLevels de objetos {value,label} vira lista de strings",
        objetos == ["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
        str(objetos),
    )
    checar(
        "privacyLevels em formato de string ainda é aceito",
        Publicador._extrair_privacidades({"privacyLevels": ["SELF_ONLY"]}) == ["SELF_ONLY"],
    )
    checar(
        "creator-info sem privacyLevels devolve lista vazia, não quebra",
        Publicador._extrair_privacidades({}) == [],
    )

    url_por_plataforma = Publicador._extrair_url(
        {"platforms": [{"platform": "tiktok", "platformPostUrl": "https://tiktok.com/x"}]}
    )
    checar(
        "platformPostUrl é lido de dentro de platforms[]",
        url_por_plataforma == "https://tiktok.com/x",
    )
    checar(
        "platformPostUrl no topo também é aceito",
        Publicador._extrair_url({"platformPostUrl": "https://tiktok.com/y"})
        == "https://tiktok.com/y",
    )
    checar(
        "post sem URL devolve None em vez de estourar",
        Publicador._extrair_url({"platforms": [{"platform": "tiktok"}]}) is None,
    )
    checar(
        "motivo da falha é extraído de dentro de platforms[]",
        "cota" in Publicador._motivo_falha(
            {"platforms": [{"platform": "tiktok", "error": "cota diária excedida"}]}
        ),
    )


def testar_credenciais_ausentes() -> None:
    print("\nComportamento sem credencial")
    from src.publicador import ErroPublicacao, Publicador

    try:
        Publicador("")
        checar("publicador recusa chave vazia com mensagem útil", False)
    except ErroPublicacao as erro:
        checar("publicador recusa chave vazia com mensagem útil", "ZERNIO_API_KEY" in str(erro))

    from src.config import segredo

    try:
        segredo("VARIAVEL_INEXISTENTE_PARA_TESTE", obrigatorio=True)
        checar("credencial obrigatória ausente aponta o .env.example", False)
    except RuntimeError as erro:
        checar("credencial obrigatória ausente aponta o .env.example", ".env.example" in str(erro))


# ---------------------------------------------------------------------- main


def main() -> int:
    print("=" * 66)
    print("Radar de Tendência — verificação")
    print("=" * 66)

    for bloco in (
        testar_config,
        testar_selecao,
        testar_guardrails,
        testar_midia,
        testar_integracoes,
        testar_parsers_do_publicador,
        testar_credenciais_ausentes,
    ):
        try:
            bloco()
        except Exception as erro:
            checar(f"bloco {bloco.__name__} concluiu", False, f"{type(erro).__name__}: {erro}")

    aprovados = sum(1 for ok, _, _ in _resultados if ok)
    total = len(_resultados)
    print("\n" + "=" * 66)
    print(f"{aprovados}/{total} verificações passaram")
    if aprovados < total:
        print("\nFalhas:")
        for ok, nome, detalhe in _resultados:
            if not ok:
                print(f"  - {nome}" + (f" — {detalhe}" if detalhe else ""))
    print("=" * 66)
    return 0 if aprovados == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
