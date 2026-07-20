# Radar de Tendência — GoCase

Automação que transforma **um sinal de tendência em uma capinha publicada no
TikTok**, sem intervenção humana: escolhe o tema, cria a arte, compõe o produto,
monta o vídeo vertical e publica — com a divulgação de conteúdo gerado por IA
que a plataforma exige.

Business case para o processo seletivo de Estágio em RPA na **GoCase (GoGroup)**.
Área de negócio: Marketing e Aquisição.

**Serviço no ar:** `https://radar-tendencia-gocase.onrender.com`

> **Primeira execução do dia.** O serviço está hospedado em plano gratuito e
> hiberna após alguns minutos sem uso; a primeira chamada leva cerca de 50
> segundos para acordá-lo. Uma execução completa leva cerca de 3 minutos nesse
> plano — o processador é lento e a codificação do vídeo domina o tempo. O
> fluxo n8n consulta o estado a cada 15 segundos e esse tráfego contínuo
> impede a hibernação no meio do trabalho.

---

## O problema

A GoCase fabrica sob demanda. Isso é uma vantagem estrutural que quase ninguém
no varejo tem: **não existe estoque para escoar antes de lançar algo novo.** Se
uma estética viraliza numa terça, ela pode estar impressa numa capinha na
terça.

O gargalo não é a fábrica — é o marketing. Entre perceber a tendência e ter um
post no ar existem um briefing, um designer, uma aprovação e uma fila de
publicação. Quando o material sai, a janela de atenção já fechou. A vantagem de
produção vira desvantagem de velocidade.

Esta automação fecha o ciclo: **do sinal ao post publicado, em minutos, sem
ninguém no meio.**

---

## Como funciona

```
sinal de tendência + produto do catálogo
        ↓
IA redige: conceito de arte, gancho, legenda, hashtags     ← guardrails de marca
        ↓
arte gerada  →  composta na capinha  →  animada em 9:16    ← o ativo imprimível
        ↓
publicação no TikTok + confirmação de status
        ↓
relatório da execução
```

O vídeo não é um quadro parado com zoom. A arte é gerada em vetor, com os
elementos separados, então a montagem dela vira a própria narrativa:

```
0,0 – 2,4 s   a arte se desenha, elemento por elemento
2,4 – 3,2 s   a arte vira produto
3,2 – 8,0 s   a capinha, com aproximação lenta
```

Isso importa porque um quadro estático com zoom é linguagem de banco de
imagens, não de TikTok — e a plataforma premia corte e movimento.

O operador abre o fluxo no n8n e clica em executar. Ou habilita o gatilho
agendado e não abre mais.

---

## Resultado medido

Execução real, conta de teste `@demogocase`, sem intervenção manual em nenhuma
etapa:

| Métrica | Valor |
|---|---|
| Tempo total, do sinal à confirmação | 54 s local · **235 s** no serviço publicado |
| Custo por execução | ~US$ 0,04 |
| Vídeo entregue | 1080×1920, H.264 yuv420p, 30 fps, faixa AAC, 8,00 s |
| Tamanho | ~1 MB, contra um teto de 25 MB |
| Estado final | `published` |
| Intervenção humana | nenhuma |

A diferença de tempo entre a máquina local e o serviço publicado é o
processador do plano gratuito: a codificação do vídeo domina, e lá ela é cerca
de quatro vezes mais lenta.

O material produzido: tendência *cultura gamer, paleta neon e cyber* → produto
*Capinha iPhone 15 Pro* → gancho *"POV: sua capinha virou setup gamer"* → arte
vetorial, mockup, vídeo vertical e post entregue.

Execuções anteriores cobriram outras tendências do catálogo — *festa junina*
produziu bandeirinhas, balões e fogueira; *ilustração botânica* produziu folhas
de monstera e samambaia. A arte acompanha o tema, não é decoração fixa.

A confirmação não veio do log do próprio sistema, e sim da TikTok: o aplicativo
notificou a conta com *"Seu conteúdo está pronto — Edite seu vídeo antes de
compartilhar no TikTok"*. Ou seja, o vídeo saiu do código, foi hospedado, foi
buscado pela TikTok, passou pelo processamento dela e chegou ao criador.

> **Sobre o modo desta execução.** Rodou em Creator Inbox, que percorre a
> integração inteira sem tornar nada público. É o modo de teste correto: prova
> todo o caminho — geração, upload, autorização, aceite da especificação do
> vídeo — sem consumir a decisão irreversível de publicar. Trocar para
> publicação direta é uma flag, e usa o mesmo código já exercitado aqui.

---

## Por que a IA gera a **arte**, não o vídeo inteiro

Esta é a decisão de arquitetura central do projeto.

Pedir a um modelo de vídeo *"uma capinha da GoCase com arte retrô dos anos 90"*
devolve um celular genérico, com arte aproximada e texto ilegível. Modelos de
vídeo não renderizam produto específico com fidelidade — e, mais importante,
**um clipe de vídeo não é imprimível.**

O que a GoCase vende é a arte. Então a arte é o que a IA gera, na proporção real
da área de impressão do produto — alta, cerca de 1:2, não quadrada. A composição
no produto é feita por código, o que garante que a capinha do vídeo é exatamente
a capinha que a fábrica produziria.

O movimento vem depois, e na maior parte das execuções nem precisa de IA: como a
arte é vetorial, a própria montagem dela vira animação.

O resultado é que **cada execução produz um ativo de negócio reutilizável**, não
só um post descartável.

---

## Por que não a API oficial da TikTok

Registro de decisão de engenharia, porque a pergunta é legítima.

A Content Posting API da TikTok existe e funciona. Mas tem **dois portões
distintos**, que costumam ser confundidos:

| Portão | O que libera |
|---|---|
| **App Review** | tira o app do sandbox |
| **Audit** | tira a restrição de visibilidade |

Enquanto o cliente de API **não é auditado**, a documentação oficial é
explícita: todo post sai em `SELF_ONLY`, a conta do usuário precisa estar
privada no momento da publicação, e o limite é de 5 usuários por 24 horas. Ou
seja — o post existe, e ninguém além do dono o vê.

E a auditoria exige uma **interface inspecionável**: tela de publicação com
avatar e nome do criador, seletor de privacidade, toggles de Duet, Stitch e
comentários, e divulgação de conteúdo comercial. Um fluxo n8n headless não tem
interface a auditar. **Não é uma questão de prazo — é inaprovável por
definição.**

A solução legítima é o modelo de parceiro desenhado pela própria TikTok: um
cliente já auditado atua como transporte, e o usuário autoriza a conta pela
tela de autorização do `tiktok.com` — nunca entregando senha a terceiro.

O transporte escolhido foi o **Zernio**. A escolha foi decidida por teste, não
por marketing: a recomendação inicial era outro serviço, com nó n8n oficial. O
teste de aceitação — conectar a conta e publicar manualmente, conferindo se o
post sai público — inverteu a decisão.

Os campos de conformidade não são opcionais e estão no código:

| Campo | Valor | Por quê |
|---|---|---|
| `video_made_with_ai` | `true` | O conteúdo é gerado por IA. Exigência de política da TikTok. |
| `commercialContentType` | `brand_organic` | A GoCase promove o próprio negócio, não parceria paga. |
| `content_preview_confirmed` | `true` | Exigência legal da plataforma. |
| `express_consent_given` | `true` | Exigência legal da plataforma. |

---

## Armadilhas de plataforma tratadas no código

Quase todos os itens abaixo vieram da documentação do fornecedor, antes de
quebrarem. A exceção está marcada — e é justamente a que nenhuma leitura teria
encontrado.

| Armadilha | Tratamento |
|---|---|
| Ferramentas de workflow reusam `x-request-id`; chamadas seguintes devolvem o post da primeira, silenciosamente | UUID novo por chamada |
| Conteúdo idêntico na mesma conta em 24h retorna HTTP 409 | O seletor evita combinações recentes e registra histórico |
| Níveis de privacidade variam por criador; usar um inválido faz o post falhar | Consulta `creator-info` antes e rebaixa para uma opção permitida |
| ~13% de falha de publicação na plataforma | Polling de status até o estado final; nunca fire-and-forget |
| Upload direto recusa acima de 25 MB | Verificação antes do envio e recompressão automática |
| Google Drive e Dropbox devolvem HTML, não vídeo | A mídia é hospedada pelo próprio transporte |
| Vídeo sem faixa de áudio processa de forma menos confiável | Faixa silenciosa injetada quando a origem não tem áudio |
| Conta pode estar no limite diário sem que a publicação avise | `canPostMore` é consultado antes; 429 vira mensagem legível |
| Conta conectada mas com token morto falha tarde e mal | Contas com `needsReconnection` são descartadas na descoberta |
| Conteúdo de parceria paga é recusado com visibilidade privada | Combinação `brand_content` + `SELF_ONLY` é barrada antes do envio |
| **Descoberta em produção:** máximo de 5 rascunhos pendentes por conta em 24h — e `creator-info` reporta `canPostMore: true` mesmo com a fila cheia, porque mede a cota de publicação e não a de rascunhos | Erro é traduzido em instrução: finalize rascunhos no aplicativo ou publique direto |

---

## Camada de IA — e onde ela **não** decide

A IA escreve o conceito e o texto. Ela não tem a palavra final sobre o que vai
ao ar.

As proibições de marca vivem no `config.yaml` (preço, prazo de entrega,
comparação com concorrente, superlativo sem lastro, saúde/política/religião).
Elas entram no prompt **e são verificadas por código depois da geração**. Se o
texto violar uma regra, o pipeline barra em vez de publicar.

O motivo é simples: **modelo de linguagem é bom em seguir instrução, mas não é
mecanismo de garantia.** Confiar só no prompt é confiar na sorte.

A verificação normaliza acentos antes de comparar — sem isso, *"revolucionária"*
seria barrado e *"revolucionaria"* passaria, e um modelo produz as duas formas.

O formato da resposta também não é pedido por prompt: é imposto pela API via
JSON Schema (`output_config.format`). Pedir "responda em JSON" e torcer é o modo
mais comum de quebrar pipeline em produção.

---

## Degradação graciosa

O pipeline nunca trava por indisponibilidade de IA de mídia.

A arte tem três caminhos, tentados em ordem:

| # | Caminho | O que entrega | `etapas.arte` |
|---|---|---|---|
| 1 | Gerador de imagem | maior alcance visual: textura, pintura, grão | `imagem_ia` |
| 2 | Vetor desenhado pela IA de texto | acerta o tema; SVG escala sem perda e separa cores | `vetor_ia` |
| 3 | Composição geométrica local | sempre disponível, na paleta da marca | `local` |

O vídeo também tem três, e a ordem não é a mesma da arte:

| # | Caminho | O que entrega | `etapas.video` |
|---|---|---|---|
| 1 | Animação por IA sobre o mockup | movimento de câmera realista | `ia` |
| 2 | Montagem em cenas a partir das camadas do vetor | narrativa: arte se monta, vira produto | `cenas` |
| 3 | Ken Burns em FFmpeg sobre o mockup | aproximação lenta, sempre disponível | `local` |

O caminho 2 só existe porque a arte veio em vetor. Achatar o SVG num PNG
descartaria a estrutura em elementos — que é exatamente o que permite animar a
montagem sem IA de vídeo, sem chave e sem cota.

**Isto não é hipótese — foi exercitado.** O plano gratuito do provedor de
imagem concede `limit: 0` para geração de imagem e de vídeo; a cota exige
faturamento com aporte mínimo. O pipeline caiu para o caminho 2 sozinho, e o
resultado da seção anterior é justamente esse caminho. A automação entregou sem
intervenção, e o relatório registrou qual rota usou.

Vetor, aliás, é o formato mais adequado à produção sob demanda: escala para
qualquer tamanho de capinha sem perder qualidade e separa cores para impressão.
O `.svg` fica salvo ao lado do `.png` — é o arquivo que a fábrica usaria.

Como efeito colateral do desenho, **a suíte de testes roda sem nenhuma
credencial**.

---

## Arquitetura

Responsabilidade única por módulo — cada arquivo faz uma coisa e é testável
isoladamente.

| Módulo | Responsabilidade |
|---|---|
| `src/tendencia.py` | Seleciona sinal e produto; evita repetir combinações. |
| `src/criativo.py` | IA de texto com schema imposto; verifica os guardrails de marca. |
| `src/arte.py` | Gera a arte imprimível. Caminho de IA e caminho local. |
| `src/mockup.py` | Compõe a arte na capinha. Garante fidelidade de produto. |
| `src/video.py` | Anima e normaliza para a especificação da TikTok. |
| `src/publicador.py` | Publicação e confirmação de status. Trata as armadilhas da plataforma. |
| `src/agente.py` | `executar_pipeline`: o fluxo completo, em uma função só. |
| `src/config.py` | Carrega `config.yaml` com fallback embutido. |
| `api.py` | Superfície HTTP com jobs assíncronos. |
| `main.py` | Execução por terminal, para desenvolvimento e evidência. |

**Fonte única de verdade.** O fluxo vive em `executar_pipeline`; a API HTTP, o
terminal e os testes chamam a mesma função. Nenhum deles reimplementa etapa.

**Por que jobs assíncronos.** A geração de vídeo leva de 1 a 3 minutos. Nenhum
request HTTP síncrono sobrevive a isso — nem no n8n, nem em plano gratuito, nem
em proxy nenhum. O n8n dispara, recebe um `job_id` e consulta até o estado
final. O polling ainda mantém tráfego constante, o que impede o serviço de
hibernar no meio da execução.

### Tecnologias

Python 3.12+ · Pillow (composição e animação por quadros) · svglib, reportlab e pypdfium2
(rasterização vetorial) · FFmpeg via `imageio-ffmpeg` · FastAPI e uvicorn (API
HTTP) · PyYAML (configuração externa) · Anthropic Claude (redação e arte
vetorial, ambas com schema imposto) · Google Gemini (imagem e vídeo, opcional) ·
Zernio (transporte de publicação) · n8n (orquestração low-code) · Render
(hospedagem).

Nenhuma dependência de biblioteca do sistema. FFmpeg e o rasterizador de PDF
vêm como binário dentro do pacote pip — decisão tomada para que o projeto suba
num runtime onde não existe `apt-get`.

### Controle de custo

Geração de imagem e de vídeo por IA têm preços muito diferentes — vídeo custa
cerca de 30 vezes mais por execução. Por isso cada uma tem seu próprio
interruptor no `config.yaml` (`usar_ia_imagem`, `usar_ia_video`), e o vídeo vem
desligado. Habilitar faturamento no provedor não deve abrir as duas torneiras
sem alguém escolher.

---

## Configuração sem código

Tudo que um time de marketing ajustaria vive no `config.yaml`, fora do código:

- **Voz e paleta da marca** — trocar a paleta repinta todo o material gerado.
- **Proibições** — a lista que os guardrails verificam.
- **Catálogo de produtos** — SKU, nome, linha e área de impressão.
- **Sinais de tendência** — tema e público de cada gatilho.
- **Especificação do vídeo** — resolução, duração, taxa de quadros.
- **Parâmetros de publicação** — privacidade, comentários, Duet, Stitch.

Configuração ausente ou inválida não derruba nada: o sistema avisa e usa os
padrões embutidos.

Credenciais nunca ficam em arquivo versionado nem no JSON do workflow — só em
variáveis de ambiente. O contrato está em [`.env.example`](.env.example).

---

## Qualidade

`testar.py` executa **41 verificações** sem exigir credencial: carga e
degradação da configuração, rotação de tendências, os guardrails de marca caso a
caso, o pipeline de mídia completo com conferência da especificação real do
vídeo (H.264, yuv420p, 1080×1920, faixa de áudio, duração e tamanho), a
integridade do workflow n8n (conexões e referências resolvem, sem credencial e
sem caminho de disco), o parsing das respostas da API de publicação e o
comportamento das superfícies quando falta chave.

Defeitos reais encontrados durante a construção e cobertos por regressão:

| Defeito | Como apareceu |
|---|---|
| Paleta da arte de reserva escapando da identidade da marca | Inspeção visual do material gerado |
| Contraste insuficiente: a última linha do texto sumia sobre o produto | Inspeção visual de um quadro do vídeo |
| Guardrail cego a superlativo sem acento | Teste caso a caso |
| Guardrail com limite de palavra impedindo `eleic` de casar com `eleição` | Teste caso a caso |
| Níveis de privacidade lidos como texto quando a API devolve objetos | Revisão linha a linha contra a documentação |
| Dois conceitos distintos de "rascunho" tratados como um só | Revisão linha a linha contra a documentação |
| Sombra da arte desenhada como retângulo sólido, lendo como moldura preta | Inspeção do vídeo montado |
| Produto e CTA escritos sobre a arte na cena de abertura | Inspeção do vídeo montado |
| Limite de 5 rascunhos pendentes por conta em 24h, não tratado | **Execução real repetida**, com a conta acumulando histórico |

Dois merecem nota porque nenhum apareceria em teste que não olhasse o formato de
resposta. O de privacidade rebaixaria toda publicação para um valor inválido. O
de rascunho é mais sutil: o serviço de transporte tem um rascunho próprio, que
guarda o post no painel dele e **nunca chega à TikTok** — enquanto a TikTok tem
o Creator Inbox, que recebe a mídia de verdade. Tratar os dois como sinônimos
faria o modo de teste não exercitar justamente o caminho que precisava ser
testado.

O último é de outra natureza, e é o mais instrutivo. Nenhuma leitura de
documentação e nenhum teste sintético o encontraria: o limite depende do
histórico da conta nas últimas 24 horas, então só aparece depois de várias
execuções reais e acumuladas. Pior, ele é invisível antes do envio — a consulta
de capacidade do criador reporta que a conta pode postar, porque mede a cota de
publicação e não a de rascunhos.

Vale como registro de método: revisão de documentação pega uma classe de erro,
inspeção visual pega outra, e uso repetido em condição real pega uma terceira
que as duas primeiras não alcançam.

Outras salvaguardas embutidas: geração de arte determinística (o mesmo conceito
produz o mesmo arquivo, o que torna uma execução reproduzível); jobs expiram
sozinhos em 1 hora; falha de publicação preserva a etapa onde parou; e status
indeterminado nunca dispara republicação automática, para não duplicar post.

### Memória: 1011 MB → 307 MB

O serviço morria por estouro de memória no container de 512 MB assim que subiu.
Medir por estágio, antes de mexer em qualquer coisa, mostrou que arte e mockup
somavam menos de 110 MB e o FFmpeg sozinho usava 1011 MB. Três causas:

| Causa | Efeito |
|---|---|
| `-threads` do FFmpeg não controla o threading interno do libx264 — é preciso `threads=1` dentro de `-x264-params` | 906 → 336 MB |
| `-loop 1` na entrada bufferizava ~150 MB sem necessidade: o `zoompan` já multiplica o quadro único pelo parâmetro `d` | 336 → 192 MB |
| O pipeline codificava duas vezes — gerava um MP4 intermediário e o relia para aplicar a legenda | 448 → 307 MB no pico total |

A especificação exigida pela TikTok não mudou. A folga que tornou isso possível
é o tamanho do arquivo: menos de 1 MB contra um teto de 25 MB, o que permite
preset rápido com CRF baixo sem perda visível.

Registro porque a primeira hipótese estava errada — reduzi o buffer do zoom
achando que era ele, e custava 6 MB. A medição por estágio evitou horas
otimizando o lugar errado.

---

## Escopo e evolução

**Escopo desta entrega.** A publicação depende de um transporte com cliente
auditado. Uma implementação direta contra a API oficial da TikTok exigiria
construir a interface de publicação que a auditoria da plataforma requer — o
que muda a natureza do projeto, de automação para produto. É um passo consciente
do roadmap, não um esquecimento.

A API sobe **sem autenticação**, por decisão de escopo do business case. Antes
de operar com a conta real da marca, exige chave de acesso.

**Evolução natural.** Ler sinais de tendência de uma fonte real (TikTok Creative
Center, Google Trends) em vez do catálogo do `config.yaml`; realimentar o
desempenho dos posts para priorizar os temas que converteram; ligar a arte
aprovada direto na fila de produção, fechando o ciclo até a fábrica; e teste A/B
de gancho sobre a mesma arte.
