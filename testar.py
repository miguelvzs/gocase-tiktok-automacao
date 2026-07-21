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
    # Publicar é o padrão. O Creator Inbox parecia mais seguro, mas a TikTok
    # aceita no máximo 5 rascunhos pendentes por conta em 24h e não oferece API
    # para limpá-los: uma rodada de testes travava a conta.
    checar(
        "publicar é o padrão; rascunho exige opção explícita",
        modo_rascunho() is False,
    )


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


def testar_saneamento_do_svg() -> None:
    """Defesas do SVG vindo da IA: cor partida e tags que somem em silêncio."""
    print("\nSaneamento do SVG gerado")
    from src import arte

    def envolver(corpo: str) -> str:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            f"{corpo}</svg>"
        )

    # Uma cor partida por espaço matava a arte inteira com "invalid literal for
    # int() with base 16" — mensagem que nem menciona cor. Agora é reparada.
    quebrado = envolver('<rect width="100" height="100" fill="#f5 eee6"/>')
    checar(
        "cor hexadecimal partida por espaço é remendada",
        '#f5eee6' in arte._sanear_cores(quebrado),
        arte._sanear_cores(quebrado)[-40:],
    )
    # Uma versão anterior juntava "ab"+"cdef" aqui e deixava "gh" sobrando,
    # criando uma cor errada com aparência de válida. O valor inteiro precisa
    # virar hexadecimal, senão nada é tocado.
    intacto = envolver('<rect fill="#ab cdefgh"/>')
    checar(
        "valor que não vira hexadecimal inteiro não é remendado",
        arte._sanear_cores(intacto) == intacto,
    )
    checar(
        "cor partida dentro de style= também é remendada",
        "#f5eee6" in arte._sanear_cores(envolver('<rect style="fill:#f5 eee6"/>')),
    )

    # clipPath, mask, pattern e filter são aceitos pelo interpretador e
    # descartados no desenho: a peça sairia errada sem nenhum erro.
    for tag, corpo in (
        ("clipPath", '<defs><clipPath id="c"><circle r="9"/></clipPath></defs>'),
        ("pattern", '<defs><pattern id="p"><circle r="3"/></pattern></defs>'),
        ("mask", '<defs><mask id="m"><rect width="9" height="9"/></mask></defs>'),
        ("script", "<script>alert(1)</script>"),
        ("use externo", '<use href="https://exemplo.com/x.svg#a"/>'),
        ("text", '<text x="10" y="10">GOCASE</text>'),
    ):
        try:
            arte._conferir_svg(envolver(corpo))
            passou = False
        except ValueError:
            passou = True
        checar(f"<{tag}> é recusado", passou)

    try:
        arte._conferir_svg(envolver('<rect fill="#zz00gg"/>'))
        legivel = False
    except ValueError as erro:
        legivel = "cor" in str(erro).lower()
    checar("cor inválida vira erro que diz ser cor", legivel)

    # `use` local é o que torna textura densa barata em tokens; só o destino
    # externo é perigoso.
    com_use = envolver(
        '<defs><circle id="p" r="2" fill="#fff"/></defs>'
        '<use href="#p" x="10" y="10"/><use xlink:href="#p" x="30" y="20"/>'
    )
    checar(
        "namespace do xlink ausente é declarado em vez de derrubar a peça",
        "xmlns:xlink" in arte._sanear_namespace(com_use),
    )
    checar(
        "<use> apontando para o próprio documento é aceito",
        arte._conferir_svg(arte._sanear_namespace(com_use)) is None,
    )

    checar(
        "SVG saudável com os recursos novos passa",
        arte._conferir_svg(
            envolver(
                '<defs><radialGradient id="r"><stop offset="0" stop-color="#ffd166"/>'
                '</radialGradient></defs>'
                '<rect width="100" height="100" fill="url(#r)" fill-opacity="0.6"/>'
                '<g transform="rotate(12 50 50)"><path d="M10 10 L90 90" '
                'stroke="#1a1a2e" stroke-dasharray="4 2"/></g>'
            )
        )
        is None,
    )


def testar_fonte_com_acentos() -> None:
    """A fonte precisa desenhar acentos no ambiente publicado, não só aqui.

    Este bloco existe por causa de um defeito que chegou ao ar: um post saiu com
    "Arraiá em versão ilustração" impresso como "Arrai□ em vers□o ilustra□□o".
    A imagem de execução não traz nenhuma fonte do sistema, então a seleção caía
    na fonte embutida do Pillow, que não cobre latim acentuado. Nenhum teste
    pegava porque todos rodavam em máquina com fontes instaladas.

    A verificação decisiva é a última: ela ignora as fontes do sistema e exige
    que a alternativa embarcada, a única presente no container, dê conta.
    """
    print("\nFonte do texto em tela")
    from PIL import Image, ImageDraw, ImageFont
    from src import video

    fonte = video._fonte(48)
    checar(
        "fonte escolhida desenha acentos",
        video._desenha_acentos(fonte),
        Path(video._caminho_fonte()).name,
    )

    # Nenhum acento pode sair como a caixa de glifo ausente.
    def marca(texto: str) -> bytes:
        imagem = Image.new("L", (400, 80), 0)
        ImageDraw.Draw(imagem).text((4, 2), texto, font=fonte, fill=255)
        return imagem.tobytes()

    checar(
        "palavra acentuada difere da mesma sem acento",
        marca("Arraiá versão ilustração") != marca("Arraia versao ilustracao"),
    )

    embarcada = ImageFont.truetype(video._fonte_embarcada(), 48)
    checar(
        "fonte embarcada cobre acentos sem o sistema operacional",
        video._desenha_acentos(embarcada),
        "reportlab/fonts/VeraBd.ttf",
    )


def testar_assinatura_de_marca() -> None:
    """O logotipo é opcional e sua ausência não pode derrubar a publicação."""
    print("\nAssinatura de marca")
    from src.config import carregar
    from src import video

    cfg = carregar()
    v = cfg["video"]
    TRABALHO.mkdir(parents=True, exist_ok=True)

    checar(
        "config declara o caminho do logotipo",
        bool(cfg["marca"].get("logo")),
        str(cfg["marca"].get("logo")),
    )

    sem_logo = _texto_termina_em(video, "sem_logo", reserva=0)
    com_logo = _texto_termina_em(video, "com_logo", reserva=140)
    checar(
        "texto sobe quando há logotipo, para não disputar a faixa",
        com_logo < sem_logo,
        f"{com_logo * 100:.0f}% contra {sem_logo * 100:.0f}%",
    )
    checar(
        "texto continua dentro da área coberta pela interface",
        max(com_logo, sem_logo) <= video.ZONA_SEGURA_BASE,
    )

    caminho_mockup = TRABALHO / "mockup.png"
    if caminho_mockup.exists():
        saida, _ = video.montar(
            mockup=caminho_mockup,
            destino=TRABALHO / "sem_marca.mp4",
            gancho="Teste sem assinatura",
            cta="Monte a sua",
            produto="Capinha iPhone 15 Pro",
            paleta=cfg["marca"]["paleta"],
            largura=v["largura"],
            altura=v["altura"],
            fps=v["fps"],
            duracao=v["duracao_segundos"],
            zoom=v["fallback_zoom"],
            api_key=None,
            logo=None,
        )
        checar("vídeo é montado mesmo sem o arquivo de logotipo", saida.exists())


def _texto_termina_em(video_mod, variante: str, reserva: int = 0) -> float:
    """Fração da altura onde o último pixel de texto aparece."""
    import numpy as np
    from PIL import Image

    from src.config import carregar

    cfg = carregar()
    v = cfg["video"]
    caminho = video_mod._desenhar_legenda(
        destino=TRABALHO / f"leg_{variante}.png",
        gancho="Um gancho de abertura",
        cta="Monte a sua",
        produto="Capinha iPhone 15 Pro",
        paleta=cfg["marca"]["paleta"],
        largura=v["largura"],
        altura=v["altura"],
        com_base=(variante != "abertura"),
        reserva_base=reserva,
    )
    with Image.open(caminho) as img:
        pixels = np.array(img.convert("RGBA"))
    eh_texto = (pixels[:, :, 3] > 200) & (pixels[:, :, :3].max(axis=2) > 120)
    linhas = np.where(eh_texto.sum(axis=1) > 20)[0]
    return float(linhas.max()) / v["altura"] if len(linhas) else 0.0


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
        testar_saneamento_do_svg,
        testar_fonte_com_acentos,
        testar_assinatura_de_marca,
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
