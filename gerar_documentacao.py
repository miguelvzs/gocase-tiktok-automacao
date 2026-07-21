"""Gera o PDF de documentação da automação.

Mesmo padrão editorial do Desafio 1: A4, Helvetica, capa, cabeçalho corrido e
seções numeradas. O conteúdo vive aqui como estrutura de dados para que uma
atualização de número medido seja uma linha, não uma diagramação nova.

    python gerar_documentacao.py

Recurso de apoio ao business case, não parte do pipeline: nada em src/ importa
este arquivo.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

TITULO = "Radar de Tendência GoCase"
SUBTITULO = "Documentação da Automação"
LINHA_CABECALHO = "Radar de Tendência GoCase · Documentação"
DATA = "21/07/2026"

AZUL = colors.HexColor("#105BA7")
GRAFITE = colors.HexColor("#2E3338")
CINZA = colors.HexColor("#6B7280")
CINZA_CLARO = colors.HexColor("#F3F4F6")
BORDA = colors.HexColor("#D9DDE2")


# ------------------------------------------------------------------- estilos


def _estilos() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "capa_titulo": ParagraphStyle(
            "capa_titulo", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=30, leading=35, textColor=AZUL, alignment=TA_CENTER,
        ),
        "capa_sub": ParagraphStyle(
            "capa_sub", parent=base["Normal"], fontName="Helvetica",
            fontSize=15, leading=20, textColor=GRAFITE, alignment=TA_CENTER,
        ),
        "capa_nota": ParagraphStyle(
            "capa_nota", parent=base["Normal"], fontName="Helvetica",
            fontSize=10.5, leading=16, textColor=CINZA, alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=15, leading=19, textColor=AZUL,
            spaceBefore=16, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=11.5, leading=15, textColor=GRAFITE,
            spaceBefore=11, spaceAfter=5,
        ),
        "texto": ParagraphStyle(
            "texto", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, leading=14.5, textColor=GRAFITE,
            alignment=TA_JUSTIFY, spaceAfter=7,
        ),
        "lista": ParagraphStyle(
            "lista", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, leading=14.5, textColor=GRAFITE,
            leftIndent=14, bulletIndent=4, spaceAfter=4,
        ),
        "nota": ParagraphStyle(
            "nota", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8.8, leading=12.5, textColor=CINZA,
            alignment=TA_JUSTIFY, spaceBefore=3, spaceAfter=9,
            leftIndent=8, rightIndent=8,
        ),
        "celula": ParagraphStyle(
            "celula", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, leading=12, textColor=GRAFITE,
        ),
        "celula_cab": ParagraphStyle(
            "celula_cab", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9, leading=12, textColor=colors.white,
        ),
    }


E = _estilos()


# ------------------------------------------------------------------ helpers


def p(texto: str) -> Paragraph:
    return Paragraph(texto, E["texto"])


def h1(texto: str) -> Paragraph:
    return Paragraph(texto, E["h1"])


def h2(texto: str) -> Paragraph:
    return Paragraph(texto, E["h2"])


def nota(texto: str) -> Paragraph:
    return Paragraph(texto, E["nota"])


def itens(*linhas: str) -> list:
    return [Paragraph(f"• {t}", E["lista"]) for t in linhas]


def tabela(cabecalho: list[str], linhas: list[list[str]], larguras: list[float]) -> Table:
    dados = [[Paragraph(c, E["celula_cab"]) for c in cabecalho]]
    dados += [[Paragraph(c, E["celula"]) for c in linha] for linha in linhas]
    t = Table(dados, colWidths=[l * cm for l in larguras], repeatRows=1, hAlign="LEFT")
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDA),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(dados)):
        if i % 2 == 0:
            estilo.append(("BACKGROUND", (0, i), (-1, i), CINZA_CLARO))
    t.setStyle(TableStyle(estilo))
    return t


def bloco(*flowables) -> KeepTogether:
    """Mantém título e tabela na mesma página."""
    return KeepTogether(list(flowables))


# ------------------------------------------------------------------ páginas


def _capa(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(AZUL)
    canvas.rect(0, A4[1] - 1.1 * cm, A4[0], 1.1 * cm, stroke=0, fill=1)
    canvas.rect(0, 0, A4[0], 0.7 * cm, stroke=0, fill=1)
    canvas.restoreState()


def _miolo(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(CINZA)
    canvas.drawString(
        2 * cm, A4[1] - 1.3 * cm, f"{LINHA_CABECALHO} · Página {doc.page}"
    )
    canvas.setStrokeColor(BORDA)
    canvas.setLineWidth(0.4)
    canvas.line(2 * cm, A4[1] - 1.5 * cm, A4[0] - 2 * cm, A4[1] - 1.5 * cm)
    canvas.restoreState()


# ----------------------------------------------------------------- conteúdo


def conteudo() -> list:
    f: list = []

    # ---------------------------------------------------------------- capa
    f += [
        Spacer(1, 5.5 * cm),
        Paragraph(TITULO, E["capa_titulo"]),
        Spacer(1, 0.7 * cm),
        Paragraph(SUBTITULO, E["capa_sub"]),
        Spacer(1, 0.3 * cm),
        Paragraph(
            "Da tendência ao post publicado no TikTok, sem intervenção humana",
            E["capa_nota"],
        ),
        Spacer(1, 4.5 * cm),
        Paragraph("Business Case — Processo Seletivo de Estágio em RPA", E["capa_nota"]),
        Paragraph("GoCase (GoGroup) — Extrema/MG", E["capa_nota"]),
        Paragraph(f"Data: {DATA}", E["capa_nota"]),
        Paragraph("Área de negócio: Marketing e Aquisição", E["capa_nota"]),
        NextPageTemplate("miolo"),
        PageBreak(),
    ]

    # ------------------------------------------------------------- 1. resumo
    f += [
        h1("1. Sumário Executivo"),
        p(
            "O Radar de Tendência transforma uma tendência real em uma capinha "
            "publicada no TikTok sem nenhuma intervenção humana. Ele lê o que o país "
            "está pesquisando agora, decide o que disso pode virar estampa, escreve o "
            "texto com a voz da marca, desenha a arte imprimível, compõe essa arte no "
            "produto, monta o vídeo vertical, publica na plataforma e acompanha até a "
            "confirmação de que o post está no ar."
        ),
        p(
            "A GoCase fabrica sob demanda, o que significa que não há estoque a escoar "
            "antes de lançar algo novo. Essa é uma vantagem estrutural rara no varejo — "
            "mas ela só se realiza se o marketing acompanhar a velocidade da fábrica. "
            "Entre perceber uma tendência e ter um post no ar existem um briefing, um "
            "designer, uma aprovação e uma fila de publicação. Quando o material sai, a "
            "janela de atenção já fechou, e a vantagem de produção vira desvantagem de "
            "velocidade."
        ),
        h2("Resultado medido em execução real"),
        tabela(
            ["Métrica", "Valor"],
            [
                ["Tempo total, da tendência ao post confirmado", "82,5 segundos"],
                ["Intervenção humana", "nenhuma"],
                ["Estado final na plataforma", "published (publicado)"],
                ["Custo por execução", "cerca de US$ 0,05"],
                ["Vídeo entregue", "1080×1920, H.264, 30 fps, 8 segundos"],
                ["Ativo reaproveitável gerado", "arte vetorial imprimível (.svg)"],
                ["Tendências lidas e triadas", "10 lidas, 10 recusadas com motivo"],
            ],
            [8.5, 8.5],
        ),
        nota(
            "O serviço está publicado e operante. A execução acima publicou de fato em "
            "uma conta de teste, e o estado foi confirmado junto à própria plataforma — "
            "não apenas registrado no log do sistema."
        ),
    ]

    # ------------------------------------------------------------ 2. problema
    f += [
        h1("2. O Problema"),
        p(
            "O gargalo do marketing de tendências não é criativo, é operacional. Uma "
            "estética que viraliza numa terça-feira precisa de material publicado ainda "
            "na terça. O processo tradicional não entrega nesse prazo, e cada etapa "
            "manual soma horas a um ciclo que compete com a atenção do público."
        ),
        h2("O que custa caro hoje"),
        *itens(
            "<b>Latência de decisão</b> — a tendência é percebida, mas o material só "
            "existe dias depois, quando o assunto já saiu de circulação.",
            "<b>Dependência de agenda</b> — designer e aprovador são recursos "
            "compartilhados; a publicação espera a fila deles.",
            "<b>Custo por peça</b> — cada post exige trabalho humano proporcional, o "
            "que inviabiliza testar muitos temas.",
            "<b>Arte descartável</b> — o material produzido serve ao post e morre ali, "
            "sem virar produto.",
        ),
        h2("O que a automação faz — e o que não faz"),
        p(
            "<b>Dentro do escopo:</b> ler as tendências reais e triá-las, selecionar tema "
            "e produto, redigir o texto sob as "
            "regras de marca, gerar a arte imprimível, compor o mockup do produto, "
            "montar o vídeo na especificação da plataforma, publicar e confirmar."
        ),
        p(
            "<b>Fora do escopo, por decisão:</b> escolher a trilha sonora (não existe "
            "API de música licenciada, nem oficial nem por intermediário) e aprovar "
            "conteúdo que viole as regras de marca — nesse caso a execução para em vez "
            "de publicar."
        ),
    ]

    # ------------------------------------------------------------------ 3. uso
    f += [
        h2("O radar, e por que ele recusa quase tudo"),
        p(
            "O sistema lê o que o país está pesquisando agora e decide o que disso "
            "pode virar estampa. A parte contraintuitiva é que sua função principal "
            "é <b>recusar</b>. Numa leitura real, as dez altas do momento eram "
            "política, processo judicial, notícia financeira, clube de futebol, nome "
            "de pessoa e um provável acidente rodoviário. Nenhuma virava estampa, e "
            "várias violavam diretamente as regras da marca."
        ),
        bloco(
            tabela(
                ["Barrado sem exceção", "Motivo"],
                [
                    ["Política, eleição, processo, investigação", "Regra de marca e risco reputacional"],
                    ["Tragédia, acidente, crime, morte, doença", "Não se estampa desgraça"],
                    ["Pessoa real — artista, atleta, influenciador", "Direito de imagem"],
                    ["Marca, empresa, produto de terceiro", "Propriedade alheia"],
                    ["Clube, seleção, competição com dono", "Propriedade de marca"],
                    ["Notícia factual sem carga visual", "Não há o que desenhar"],
                ],
                [7.5, 9.5],
            ),
        ),
        p(
            "Passa apenas o que cumpre quatro condições ao mesmo tempo: é estético, "
            "cultural ou sazonal e não notícia; tem forma, cor ou textura que um "
            "ilustrador desenharia; interessa a alguém de 16 a 32 anos; e é algo que "
            "a pessoa carregaria no bolso o dia inteiro. Na dúvida, recusa. Ao "
            "aprovar, o assunto é reescrito como tema de estampa e o nome próprio "
            "que o originou desaparece."
        ),
        nota(
            "Verificado nos dois sentidos, porque testar só a recusa deixaria o "
            "caminho de aprovação sem prova: contra a leitura real, dez recusados e "
            "nenhum aprovado; contra uma lista preparada com casos aprováveis, três "
            "aprovados e quatro recusados. Quando nada passa — o caso mais comum — a "
            "escolha volta ao catálogo curado, e o relatório registra a origem do "
            "tema e o motivo de cada recusa."
        ),

        h1("3. Como a Automação é Usada"),
        p(
            "Do ponto de vista de quem opera, a execução é um clique. O fluxo de "
            "automação é aberto no navegador e disparado; todo o processamento acontece "
            "no servidor, e nada é instalado na máquina do operador."
        ),
        p(
            "O operador não escolhe tema nem produto: o sistema seleciona uma combinação "
            "ainda não utilizada do catálogo, evitando repetição — conteúdo duplicado é "
            "recusado pela plataforma dentro de 24 horas. Fixar o tema ou o produto é "
            "possível, mas opcional."
        ),
        bloco(
            h2("Três formas de acionar, uma única lógica"),
            tabela(
                ["Superfície", "Para quem", "Como funciona"],
                [
                    [
                        "Fluxo n8n",
                        "Operação",
                        "Importado uma vez; dispara com um clique ou por gatilho "
                        "diário automático.",
                    ],
                    [
                        "API HTTP",
                        "Outros sistemas",
                        "HTTP e JSON puros, sem SDK. Integra com Make, Power Automate "
                        "ou código próprio.",
                    ],
                    [
                        "Terminal",
                        "Desenvolvimento",
                        "Execução local para verificação e ajuste.",
                    ],
                ],
                [3.0, 3.0, 11.0],
            ),
        ),
        nota(
            "As três superfícies chamam a mesma função de pipeline. Nenhuma delas "
            "reimplementa uma etapa, o que impede que o comportamento divirja entre a "
            "operação e o teste."
        ),
        p(
            "Ao final, o fluxo devolve um relatório com o material produzido, o estado "
            "da publicação, o tempo de cada etapa e qual caminho técnico foi usado em "
            "cada estágio — informação que permite auditar a execução sem abrir o log."
        ),
    ]

    # -------------------------------------------------------------- 4. fluxo
    f += [
        h1("4. Fluxo de Processamento"),
        tabela(
            ["Etapa", "O que faz"],
            [
                [
                    "1. Radar",
                    "Lê as tendências reais, faz a triagem e escolhe o tema e o produto, evitando "
                    "combinações recentes.",
                ],
                [
                    "2. Criação",
                    "Em paralelo: redige o texto com voz de marca e desenha a arte "
                    "imprimível em vetor.",
                ],
                [
                    "3. Composição",
                    "Aplica a arte na silhueta do produto, com módulo de câmera, "
                    "borda, sombra e brilho.",
                ],
                [
                    "4. Vídeo",
                    "Monta o vídeo 9:16 com aproximação lenta, texto sobreposto e "
                    "assinatura da marca no encerramento.",
                ],
                [
                    "5. Publicação",
                    "Envia à plataforma com os campos de conformidade obrigatórios.",
                ],
                [
                    "6. Confirmação",
                    "Acompanha o estado do post até o desfecho e traduz recusas em "
                    "instruções acionáveis.",
                ],
            ],
            [3.2, 13.8],
        ),
        p(
            "As etapas 2 e 3 disparam simultaneamente porque partem do mesmo insumo — "
            "tendência, público e produto. A arte não precisa esperar o texto ficar "
            "pronto, e essa paralelização foi o que reduziu o tempo de execução em 42% "
            "quando medida pela primeira vez."
        ),
        p(
            "A publicação é assíncrona por natureza: a plataforma aceita o post antes de "
            "processar a mídia, e cerca de 13% dos envios falham nessa etapa invisível. "
            "Por isso a etapa 6 existe — o sistema nunca considera o trabalho concluído "
            "sem confirmação do estado final."
        ),
    ]

    # ------------------------------------------------- 5. conteúdo e marca
    f += [
        h1("5. Conteúdo e Proteção de Marca"),
        p(
            "O texto de cada post é redigido por modelo de linguagem, mas o formato da "
            "resposta não é pedido por instrução: é imposto pela API através de um "
            "esquema estruturado. Pedir “responda em JSON” e torcer é a forma mais comum "
            "de quebrar um pipeline em produção."
        ),
        p(
            "As proibições de marca são verificadas por código depois da geração. Se o "
            "texto violar uma regra, a execução para em vez de publicar."
        ),
        bloco(
            h2("Regras verificadas antes de publicar"),
            tabela(
                ["#", "Regra", "Por quê"],
                [
                    ["1", "Sem menção a preço", "Preço varia por canal e promoção."],
                    ["2", "Sem promessa de prazo de entrega", "Prazo depende de logística."],
                    ["3", "Sem comparação com concorrente", "Risco jurídico e de imagem."],
                    ["4", "Sem superlativo sem lastro", "Alegação não comprovável."],
                    ["5", "Sem tema de saúde, política ou religião", "Fora da voz da marca."],
                    ["6", "Legenda dentro do limite da plataforma", "Corte silencioso do texto."],
                ],
                [1.0, 8.0, 8.0],
            ),
        ),
        nota(
            "A verificação normaliza acentos antes de comparar. Sem isso, “revolucionária” "
            "seria barrado e “revolucionaria” passaria — e um modelo de linguagem produz "
            "as duas formas. Modelo é bom em seguir instrução, mas não é mecanismo de "
            "garantia; por isso a regra é conferida, não apenas pedida."
        ),
        h2("Conformidade obrigatória da plataforma"),
        tabela(
            ["Campo declarado", "Valor", "Motivo"],
            [
                ["Conteúdo gerado por IA", "sim", "Exigência de política da plataforma."],
                ["Tipo de conteúdo comercial", "promoção própria", "Não é parceria paga."],
                ["Pré-visualização confirmada", "sim", "Exigência legal."],
                ["Consentimento expresso", "sim", "Exigência legal."],
            ],
            [5.5, 4.0, 7.5],
        ),
    ]

    # ------------------------------------------------------- 6. entregue
    f += [
        h1("6. O Que é Entregue"),
        tabela(
            ["Artefato", "Conteúdo"],
            [
                [
                    "Post publicado",
                    "Vídeo no ar na conta, com legenda, hashtags e declarações de "
                    "conformidade.",
                ],
                [
                    "Arte vetorial (.svg)",
                    "O desenho imprimível, na proporção real da área de impressão do "
                    "produto. Escala sem perda.",
                ],
                [
                    "Arte rasterizada (.png)",
                    "A mesma arte em imagem, na resolução da área de impressão.",
                ],
                [
                    "Mockup do produto (.png)",
                    "A capinha renderizada com a arte aplicada.",
                ],
                [
                    "Vídeo (.mp4)",
                    "1080×1920, H.264, 30 fps, 8 segundos, com faixa de áudio.",
                ],
                [
                    "Relatório da execução",
                    "Tema, produto, texto, tempos por etapa, caminho técnico usado e "
                    "estado final.",
                ],
            ],
            [4.5, 12.5],
        ),
        p(
            "O ponto que diferencia esta automação de um gerador de posts: <b>cada "
            "execução produz um ativo de negócio reaproveitável</b>, não apenas material "
            "descartável. A arte sai em vetor, formato que escala sem perda e separa "
            "cores para impressão — pronta para a produção sob demanda, não só para o "
            "feed."
        ),
    ]

    # ------------------------------------------------------------- 7. a arte
    f += [
        h1("7. Por que a IA Gera a Arte, e Não o Vídeo Inteiro"),
        p(
            "Pedir a um modelo de vídeo “uma capinha da GoCase com arte retrô dos anos "
            "90” devolve um celular genérico, com arte aproximada e texto ilegível. "
            "Modelos de vídeo não renderizam produto específico com fidelidade — e, mais "
            "importante, <b>um clipe de vídeo não é imprimível</b>."
        ),
        p(
            "O que a GoCase vende é a arte. Então a arte é o que a IA gera, na proporção "
            "real da área de impressão. A composição no produto é feita por código, o que "
            "garante que a capinha exibida no vídeo é exatamente a que a fábrica "
            "produziria."
        ),
        bloco(
            h2("Três caminhos, tentados em ordem"),
            tabela(
                ["#", "Caminho", "O que entrega"],
                [
                    [
                        "1",
                        "Gerador de imagem por IA",
                        "Maior alcance visual: textura, pintura, grão.",
                    ],
                    [
                        "2",
                        "Vetor desenhado por IA de texto",
                        "Acerta o tema; escala sem perda e separa cores para impressão.",
                    ],
                    [
                        "3",
                        "Composição geométrica local",
                        "Sempre disponível, na paleta da marca, sem depender de rede.",
                    ],
                ],
                [1.0, 5.5, 10.5],
            ),
        ),
        nota(
            "Esta degradação não é hipotética. O plano gratuito do provedor de imagem "
            "concede cota zero para geração — não é limite por minuto, é ausência de "
            "cota. O pipeline caiu para o caminho 2 sozinho, e é ele que produz o "
            "material das execuções registradas neste documento. Um efeito colateral do "
            "desenho: a suíte de verificação roda sem nenhuma credencial."
        ),
    ]

    # -------------------------------------------------------- 8. arquitetura
    f += [
        h1("8. Arquitetura"),
        p(
            "Responsabilidade única por módulo: cada arquivo faz uma coisa e é "
            "verificável isoladamente. A separação existe para que uma mudança de regra "
            "não obrigue a mexer no restante do sistema."
        ),
        tabela(
            ["Módulo", "Responsabilidade"],
            [
                ["tendencia", "Seleciona sinal e produto; evita repetir combinações."],
                ["criativo", "IA de texto com esquema imposto; verifica as regras de marca."],
                ["arte", "Gera a arte imprimível; três caminhos; rasteriza o vetor."],
                ["mockup", "Compõe a arte no produto; garante fidelidade de produto."],
                ["video", "Monta o vídeo e normaliza para a especificação da plataforma."],
                ["publicador", "Publica e confirma; trata as armadilhas da plataforma."],
                ["config", "Carrega as regras externas, com valores-padrão de segurança."],
                ["agente", "Reúne o fluxo completo em uma única função."],
                ["api", "Superfície HTTP, com trabalhos assíncronos."],
            ],
            [3.2, 13.8],
        ),
        p(
            "<b>Fonte única de verdade.</b> O fluxo existe em uma função só, usada por "
            "todas as superfícies. A API HTTP, o terminal e os testes chamam a mesma "
            "função; nenhum deles reimplementa uma etapa."
        ),
        bloco(
            h2("Tecnologias empregadas"),
            tabela(
                ["Camada", "Tecnologias e papel"],
            [
                [
                    "Hospedagem",
                    "<b>Fly.io</b> — executa a API em microVM com dois núcleos "
                    "dedicados e 4 GB; desliga sozinha entre execuções e cobra por "
                    "segundo. <b>Docker</b> — empacota a aplicação.",
                ],
                [
                    "Serviço",
                    "<b>Python</b> · <b>FastAPI</b> (rotas e documentação interativa) · "
                    "<b>uvicorn</b> (servidor) · <b>Pydantic</b> (validação de entrada).",
                ],
                [
                    "Orquestração",
                    "<b>n8n</b> — dispara o trabalho, acorda o serviço, consulta o "
                    "estado em laço, ramifica entre sucesso e falha e monta o relatório.",
                ],
                [
                    "Inteligência",
                    "<b>Anthropic Claude</b> — redige o conteúdo e desenha a arte "
                    "vetorial. <b>Google Gemini</b> e <b>Veo</b> — caminhos preferenciais "
                    "de imagem e movimento quando há cota.",
                ],
                [
                    "Mídia",
                    "<b>svglib</b> e <b>reportlab</b> (vetor para PDF) · <b>pypdfium2</b> "
                    "(rasterização) · <b>Pillow</b> (composição do produto e do texto) · "
                    "<b>FFmpeg</b> (montagem e normalização do vídeo).",
                ],
                [
                    "Publicação",
                    "<b>Zernio</b> — cliente auditado que atua como transporte para a "
                    "<b>Content Posting API</b> oficial do TikTok.",
                ],
                    [
                        "Configuração",
                        "<b>PyYAML</b> (regras externas) · <b>python-dotenv</b> "
                        "(credenciais por ambiente) · <b>httpx</b> (cliente HTTP).",
                    ],
                ],
                [3.2, 13.8],
            ),
        ),
        nota(
            "Nem o FFmpeg nem o rasterizador exigem instalação no sistema operacional: "
            "ambos chegam como binário dentro do pacote Python. É o que mantém a imagem "
            "de execução em 113 MB e permite mover o projeto de máquina sem preparo."
        ),
    ]

    # ---------------------------------------------------- 9. plataforma/API
    f += [
        h1("9. A Decisão de Transporte"),
        p(
            "A API oficial de publicação do TikTok existe e funciona, mas possui dois "
            "portões distintos: um libera o aplicativo do ambiente de testes, o outro "
            "remove a restrição de visibilidade. Enquanto o cliente de API não passa por "
            "auditoria, a documentação oficial é explícita: todo post sai visível apenas "
            "para o próprio autor, a conta precisa estar privada no momento da "
            "publicação, e o limite é de cinco usuários a cada 24 horas. O post existe, e "
            "ninguém além do dono o vê."
        ),
        p(
            "A auditoria, por sua vez, exige uma <b>interface inspecionável</b>: tela de "
            "publicação com avatar e nome do criador, seletor de privacidade, controles "
            "de interação e divulgação de conteúdo comercial. Um fluxo automatizado não "
            "possui interface a auditar. <b>Não é uma questão de prazo — é inaprovável "
            "por definição.</b>"
        ),
        p(
            "A solução legítima é o modelo de parceria desenhado pela própria "
            "plataforma: um cliente já auditado atua como transporte, e a conta é "
            "autorizada pela tela oficial de autorização — sem que nenhuma senha seja "
            "entregue a terceiros."
        ),
        nota(
            "A escolha do transporte foi decidida por teste de aceitação, não por "
            "material de divulgação. A recomendação inicial era outro serviço, que "
            "oferecia integração nativa com a ferramenta de orquestração. O teste — "
            "conectar a conta e publicar manualmente, conferindo se o post saía "
            "público — inverteu a decisão."
        ),
        h2("Armadilhas de plataforma tratadas no código"),
        tabela(
            ["Armadilha", "Tratamento"],
            [
                [
                    "Ferramentas de fluxo reaproveitam o identificador da requisição, e "
                    "chamadas seguintes devolvem o post da primeira, silenciosamente",
                    "Identificador novo a cada chamada.",
                ],
                [
                    "Conteúdo idêntico na mesma conta dentro de 24 h é recusado",
                    "O seletor evita combinações recentes e registra histórico.",
                ],
                [
                    "Níveis de privacidade variam por criador; usar um inválido faz o "
                    "post falhar",
                    "Consulta as opções do criador antes e rebaixa para uma permitida.",
                ],
                [
                    "Cerca de 13% dos envios falham no processamento da plataforma",
                    "Acompanhamento até o estado final; nunca disparar e esquecer.",
                ],
                [
                    "Vídeo sem faixa de áudio processa de forma menos confiável",
                    "Faixa silenciosa injetada quando a origem não tem áudio.",
                ],
                [
                    "Conta pode estar no limite diário sem que a consulta de capacidade "
                    "avise",
                    "Capacidade consultada antes; recusa vira mensagem legível.",
                ],
                [
                    "Máximo de cinco rascunhos pendentes por conta em 24 h, sem forma de "
                    "limpá-los pela API",
                    "Publicação direta é o padrão; a recusa é traduzida em instrução.",
                ],
            ],
            [8.5, 8.5],
        ),
    ]

    # ---------------------------------------------- 10. config sem código
    f += [
        h1("10. Ajuste sem Programação"),
        p(
            "Tudo que uma equipe de marketing ajustaria vive num arquivo de "
            "configuração, fora do código:"
        ),
        *itens(
            "<b>Voz e paleta da marca</b> — governam o vídeo: texto, chamada e "
            "assinatura. A arte impressa segue a paleta do próprio tema.",
            "<b>Proibições</b> — a lista que as verificações de marca conferem.",
            "<b>Catálogo de produtos</b> — SKU, nome, linha e área de impressão real.",
            "<b>Sinais de tendência</b> — tema e público de cada gatilho.",
            "<b>Especificação do vídeo</b> — resolução, duração e taxa de quadros.",
            "<b>Parâmetros de publicação</b> — privacidade e controles de interação.",
            "<b>Interruptores de custo</b> — geração de imagem e de vídeo por IA, separados.",
        ),
        Spacer(1, 0.2 * cm),
        nota(
            "Configuração ausente ou inválida não derruba a automação: o sistema avisa e "
            "usa os valores-padrão embutidos. Credenciais nunca ficam em arquivo "
            "versionado — apenas em variáveis de ambiente do servidor."
        ),
        h2("Controle de custo"),
        p(
            "Geração de imagem e de vídeo por IA têm preços muito diferentes: vídeo custa "
            "cerca de trinta vezes mais por execução. Cada uma tem seu próprio "
            "interruptor, e o vídeo vem desligado. Habilitar faturamento no provedor não "
            "deve abrir as duas torneiras sem que alguém escolha."
        ),
    ]

    # ------------------------------------------------------- 11. qualidade
    f += [
        h1("11. Qualidade e Salvaguardas"),
        p(
            "O projeto acompanha uma verificação automatizada com <b>40 checagens</b>, "
            "que roda sem exigir nenhuma credencial."
        ),
        tabela(
            ["O que é verificado"],
            [
                ["Carga da configuração e degradação para os valores-padrão."],
                ["Rotação de tendências: combinações recentes não se repetem."],
                ["Regras de marca, caso a caso, incluindo variações com e sem acento."],
                ["Pipeline de mídia completo, com conferência da especificação real do vídeo."],
                ["Integridade do fluxo de orquestração entregue."],
                ["Interpretação das respostas da API de publicação."],
                ["Área segura do texto na tela, contra a interface da plataforma."],
                ["Comportamento das superfícies quando falta credencial."],
            ],
            [17.0],
        ),
        h2("Defeitos reais encontrados, por método de descoberta"),
        p(
            "Cada método alcançou uma classe de problema que os outros não pegavam — e é "
            "essa a informação útil:"
        ),
        tabela(
            ["Método", "O que encontrou"],
            [
                [
                    "Revisão de documentação",
                    "Níveis de privacidade lidos como texto quando a API devolve "
                    "objetos; dois conceitos distintos de “rascunho” tratados como um só.",
                ],
                [
                    "Inspeção visual do material",
                    "Paleta escapando da identidade; contraste insuficiente escondendo "
                    "texto; sombra desenhada como moldura sólida.",
                ],
                [
                    "Uso repetido em condição real",
                    "Limite de rascunhos pendentes; trabalhos perdidos em reinício de "
                    "serviço; texto oculto pela interface da plataforma.",
                ],
                [
                    "Medição instrumentada",
                    "Consumo de memória e custo de tempo por estágio, que redirecionaram "
                    "duas otimizações inteiras.",
                ],
            ],
            [4.5, 12.5],
        ),
        h2("Salvaguardas embutidas"),
        *itens(
            "Falta de cota de IA não derruba a execução: o sistema degrada para o "
            "caminho seguinte e registra qual foi usado.",
            "Ativo de marca ausente não impede a publicação; o vídeo sai sem assinatura "
            "e o relatório informa o caso.",
            "Vídeo acima do limite de tamanho é recomprimido automaticamente antes do envio.",
            "Post criado com desfecho desconhecido nunca é republicado — o identificador "
            "é devolvido para consulta manual, evitando duplicata.",
            "Trabalhos em memória expiram sozinhos após uma hora.",
        ),
    ]

    # ---------------------------------------------------------- 12. ganhos
    f += [
        h1("12. Ganhos Esperados"),
        tabela(
            ["Dimensão", "Antes (processo manual)", "Depois (automação)"],
            [
                ["Tempo até o post no ar", "Dias", "82 segundos"],
                ["Custo por peça", "Horas de designer e redator", "Cerca de US$ 0,05"],
                [
                    "Volume viável",
                    "Limitado pela agenda da equipe",
                    "Limitado pela política da plataforma",
                ],
                [
                    "Consistência de marca",
                    "Varia com o autor",
                    "Regras verificadas por código a cada peça",
                ],
                [
                    "Aproveitamento da arte",
                    "Peça descartável para o feed",
                    "Ativo vetorial pronto para impressão",
                ],
                [
                    "Rastreabilidade",
                    "Sem registro estruturado",
                    "Relatório com tempos, caminhos e estado final",
                ],
                [
                    "Conformidade",
                    "Depende de lembrar",
                    "Declarações obrigatórias enviadas sempre",
                ],
            ],
            [4.0, 6.5, 6.5],
        ),
        p(
            "Além do tempo, a automação libera a equipe criativa da produção repetitiva "
            "e permite testar muitos temas por dia — o que transforma a vantagem de "
            "fabricação sob demanda em vantagem de mercado. O tema que converter pode "
            "ser levado à produção com a arte já pronta."
        ),
    ]

    # ------------------------------------------------------- 13. decisões
    f += [
        h1("13. Decisões de Design"),
        p("Escolhas que não são evidentes apenas lendo o resultado:"),
        *itens(
            "<b>A IA gera a arte, não o vídeo.</b> O que a empresa vende é a arte, e ela "
            "precisa ser imprimível. Vídeo gerado não é ativo de produção.",
            "<b>Formato de resposta imposto por esquema, não por instrução.</b> Pedir "
            "um formato ao modelo e torcer é a falha mais comum em produção.",
            "<b>Regras de marca conferidas depois da geração.</b> Modelo de linguagem "
            "segue instrução bem, mas não é mecanismo de garantia.",
            "<b>Fidelidade de produto feita por código.</b> A capinha do vídeo é a "
            "mesma que a fábrica produz, o que um modelo de imagem não garante.",
            "<b>Trabalhos assíncronos.</b> Nenhuma requisição HTTP síncrona sobrevive a "
            "minutos de processamento, em nenhuma infraestrutura.",
            "<b>Publicação confirmada, nunca presumida.</b> A plataforma aceita antes de "
            "processar; só o estado final diz se o post existe.",
            "<b>Degradação em camadas.</b> Cada etapa cara tem um caminho reserva, o que "
            "mantém a automação operante — e testável sem credencial.",
            "<b>Cobrança por segundo em vez de preço fixo.</b> A carga é em rajada: "
            "minutos de trabalho e horas de silêncio.",
        ),
        Spacer(1, 0.15 * cm),
        h2("O caso da hospedagem, como exemplo de método"),
        p(
            "A automação nasceu num plano gratuito de preço fixo e funcionava. A "
            "instrumentação revelou que ela funcionava <b>contra</b> a plataforma: um "
            "décimo de núcleo permanente, pago o mês inteiro, com quase 24 horas diárias "
            "de ociosidade — e capacidade faltando justamente nos poucos minutos de "
            "trabalho. Codificar o vídeo levava 135 segundos."
        ),
        tabela(
            ["", "Plano de preço fixo", "Cobrança por segundo"],
            [
                ["CPU", "0,1 de um núcleo", "2 núcleos dedicados"],
                ["Memória", "512 MB", "4 GB"],
                ["Custo mensal", "US$ 7,00 (plano equivalente)", "cerca de US$ 0,50"],
                ["Execução completa", "176,2 s", "82,5 s"],
                ["Etapa de vídeo", "135,1 s", "12,7 s"],
            ],
            [4.0, 6.5, 6.5],
        ),
        nota(
            "Um núcleo dedicado saiu mais barato que meio núcleo fixo, porque não se paga "
            "pelas horas de silêncio. A previsão feita antes da migração era de 48 "
            "segundos totais; o resultado foi 64,4. A parte que dependia de hardware era "
            "previsível, a que dependia da latência de terceiros não — e as duas ficam "
            "registradas, porque errar a previsão e apontar onde errou vale mais do que "
            "apagá-la."
        ),
    ]

    # ------------------------------------------------- 14. escopo/evolução
    f += [
        h1("14. Escopo e Evolução"),
        h2("Limitações conhecidas"),
        *itens(
            "<b>Trilha sonora.</b> Não existe API de música licenciada — nem oficial da "
            "plataforma, nem por intermediário. O que faz um vídeo circular é usar um som "
            "em alta, e isso só o aplicativo oferece. O vídeo sai com faixa silenciosa.",
            "<b>Autenticação.</b> O serviço está publicado sem chave de acesso, por "
            "decisão de escopo do business case. Operar com a conta real da marca exige "
            "esse passo antes.",
            "<b>Sinais de tendência.</b> Vêm de um catálogo configurado, não de uma fonte "
            "de dados ao vivo.",
            "<b>Auditoria própria.</b> Uma implementação direta contra a API oficial "
            "exigiria construir a interface de publicação que a auditoria requer, o que "
            "muda a natureza do projeto — de automação para produto.",
        ),
        Spacer(1, 0.2 * cm),
        h2("Evolução natural"),
        *itens(
            "<b>Tendências ao vivo</b> — ler sinais de fontes reais em vez do catálogo "
            "configurado.",
            "<b>Ciclo fechado com desempenho</b> — realimentar o resultado dos posts "
            "para priorizar os temas que converteram.",
            "<b>Ligação com a produção</b> — enviar a arte aprovada direto para a fila "
            "de fabricação, fechando o ciclo até a fábrica.",
            "<b>Teste A/B de gancho</b> — variar o texto sobre a mesma arte, "
            "reaproveitando o ativo mais caro de produzir.",
            "<b>Autenticação por chave</b> — antes de operar com a conta oficial.",
        ),
        Spacer(1, 0.9 * cm),
        nota(
            "Documento produzido para o business case do processo seletivo de Estágio em "
            "RPA — GoCase (GoGroup). O plano de ação para implantação em produção é "
            "entregue em documento à parte."
        ),
    ]

    return f


def gerar(destino: Path) -> Path:
    doc = BaseDocTemplate(
        str(destino),
        pagesize=A4,
        title=f"{TITULO} — {SUBTITULO}",
        author="Business Case — Processo Seletivo de Estágio em RPA",
        subject="Automação de publicação no TikTok para produção sob demanda",
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2.1 * cm,
        bottomMargin=2 * cm,
    )
    quadro = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="corpo"
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="capa", frames=[quadro], onPage=_capa),
            PageTemplate(id="miolo", frames=[quadro], onPage=_miolo),
        ]
    )
    doc.build(conteudo())
    return destino


if __name__ == "__main__":
    caminho = Path(__file__).resolve().parent / (
        "RADAR DE TENDÊNCIA GOCASE - DOCUMENTAÇÃO.pdf"
    )
    gerar(caminho)
    print(f"Documentação gerada: {caminho.name} ({caminho.stat().st_size / 1024:.0f} KB)")
