# Radar de Tendência — GoCase

Automação que transforma **uma tendência real em uma capinha publicada no
TikTok**, sem intervenção humana: lê o que o Brasil está pesquisando agora,
decide o que disso pode virar estampa, escreve o texto, cria a arte, compõe o
produto, monta o vídeo vertical, publica e confirma o resultado.

A parte que dá nome ao projeto é a mais contraintuitiva: **o radar existe
principalmente para recusar.** Quase tudo que está em alta é notícia, e notícia
não vira estampa — ver [O radar: o trabalho é recusar](#o-radar-o-trabalho-é-recusar).

Business case para o processo seletivo de Estágio em RPA na **GoCase (GoGroup)**.
Área de negócio: Marketing e Aquisição.

**Serviço no ar:** `https://gocase-tiktok-automacao.fly.dev`
**Documentação interativa da API:** `/docs`

---

## Sumário

- [O problema](#o-problema)
- [O radar: o trabalho é recusar](#o-radar-o-trabalho-é-recusar)
- [Como funciona na prática](#como-funciona-na-prática)
- [O que acontece em cada execução](#o-que-acontece-em-cada-execução)
- [Quem faz o quê](#quem-faz-o-quê)
- [Resultado medido](#resultado-medido)
- [Decisões de arquitetura](#decisões-de-arquitetura)
  - [Por que a hospedagem mudou](#por-que-a-hospedagem-mudou)
- [Degradação graciosa](#degradação-graciosa)
- [Armadilhas de plataforma tratadas no código](#armadilhas-de-plataforma-tratadas-no-código)
- [Configuração sem código](#configuração-sem-código)
- [Qualidade](#qualidade)
- [Escopo e evolução](#escopo-e-evolução)

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

## O radar: o trabalho é recusar

O projeto se chama Radar de Tendência. A primeira versão lia um arquivo YAML —
o que é um catálogo, não um radar. A ligação com o mundo é o feed público do
**Google Trends**: endpoint oficial, sem chave e sem dependência nova.

O que decidiu o desenho não foi a fonte, foi **olhar o que ela devolve**. Numa
leitura real do Brasil:

```
8 de janeiro · deltan dallagnol · banco master · tribunal de contas
liga dos campeões · fenerbahçe · mg-188 · bianca andrade
balanço da copa · climatização
```

Política, processo judicial, notícia financeira, clube de futebol, nome de
pessoa e provável acidente rodoviário. **Nenhum vira estampa**, e vários violam
diretamente as proibições de marca.

Um radar ingênuo teria tentado desenhar uma capinha do 8 de janeiro. Daí a
inversão que dá nome a esta seção: **a função principal da triagem não é
aprovar, é recusar.** Devolver lista vazia é resultado correto e esperado.

### O que é barrado, sem exceção

| Categoria | Por quê |
|---|---|
| Política, eleição, processo, investigação | Proibição de marca e risco reputacional |
| Tragédia, acidente, crime, morte, doença | Não se estampa desgraça |
| Pessoa real — artista, atleta, influenciador | Nome de gente não se imprime sem direito de imagem |
| Marca, empresa, banco, produto de terceiro | Propriedade alheia |
| Clube, seleção, competição com dono | Propriedade de marca |
| Notícia factual sem carga visual | Não há o que desenhar |

### O que passa

Precisa cumprir as quatro condições ao mesmo tempo: ser estético, cultural ou
sazonal, e não notícia; ter forma, cor ou textura que um ilustrador desenharia;
interessar a alguém de 16 a 32 anos; e ser algo que a pessoa carregaria no bolso
o dia inteiro. **É roupa, não manchete.** Na dúvida, recusa.

Ao aprovar, o assunto é reescrito como tema de estampa e o nome próprio some.
Uma alta em `são joão 2026` vira "festa junina com bandeirinhas e clima de
arraial" — o tema, não o evento.

### Medido nos dois sentidos

Testar só a recusa deixaria o caminho de aprovação como código morto.

| Entrada | Aprovados | Recusados |
|---|---|---|
| Leitura real do Google Trends BR | **0** | **10** |
| Lista injetada com casos aprováveis | **3** | **4** |

Na lista injetada, `estetica cottagecore`, `sao joao 2026` e `unhas cromadas
aura` passaram; `8 de janeiro`, `deltan dallagnol`, `acidente br-101` e
`flamengo` foram barrados — este último como propriedade de marca.

### O catálogo não é plano B

Quando nada passa, a escolha volta para o catálogo curado de 14 movimentos
estéticos. Esse é o caminho mais frequente, e é o certo: a automação publica de
qualquer forma, e o que muda é a origem do assunto.

O relatório de cada execução registra `etapas.origem_do_tema` (`radar` ou
`catalogo`) e a lista de recusas com o motivo de cada uma — o que torna a
triagem auditável em vez de opaca.

### Nada disso pode derrubar uma publicação

Fonte fora do ar, feed vazio, triagem falhando ou credencial ausente: todos os
casos devolvem lista vazia e o catálogo assume. Uma fonte externa instável não
tem poder de parar o pipeline.

**Custo:** de 8 a 15 s no início da execução, medido em três leituras — o feed
mais uma chamada de triagem com esforço baixo, porque classificar não é criar.

---

## Como funciona na prática

Três formas de disparar, todas chamando o mesmo código:

| Forma | Uso |
|---|---|
| **Fluxo n8n** | operação do dia a dia. Abrir, clicar em executar. Ou habilitar o gatilho diário e não abrir mais. |
| **API HTTP** | integração com qualquer outra ferramenta — Make, Power Automate, cron com `curl`. |
| **Terminal** | desenvolvimento e verificação. `python main.py` |

O operador não escolhe tema nem produto: o sistema seleciona uma combinação
ainda não usada do catálogo. Fixar um dos dois é opcional.

Ao final, o fluxo devolve um relatório com o material produzido, o estado da
publicação, o tempo de cada etapa e qual caminho técnico foi usado em cada
estágio.

---

## O que acontece em cada execução

```
1. RADAR        tendências reais → triagem → tema aprovado ou catálogo
                        ↓
2. CRIAÇÃO      texto e arte, em paralelo
                        ↓
3. COMPOSIÇÃO   arte aplicada no produto
                        ↓
4. VÍDEO        9:16, com assinatura de marca no fim
                        ↓
5. PUBLICAÇÃO   TikTok, com divulgação de conteúdo gerado por IA
                        ↓
6. CONFIRMAÇÃO  acompanha até o estado final
```

### 1. Radar — de onde vem o assunto

Busca o que o Brasil está pesquisando agora no feed público do Google Trends e
submete cada termo a uma triagem. O que passa vira tema de estampa; o que não
passa é registrado com o motivo. Quando nada passa — o caso mais comum —, o
catálogo curado assume.

O detalhe que define o desenho está na seção
[O radar: o trabalho é recusar](#o-radar-o-trabalho-é-recusar).

Em seguida entra o produto: um catálogo com SKU, nome, linha e área de
impressão. A combinação escolhida evita as recentes, porque conteúdo repetido é
recusado pela plataforma de publicação dentro de 24 horas — e o histórico dessas
combinações vive num volume, para sobreviver ao deploy.

Cada sinal é um movimento estético específico — Y2K cromado, coquette, traço de
mangá, grafite — e não uma categoria vaga. A diferença aparece no desenho:
"estética retrô" deixa a escolha visual inteira para o modelo, que resolve pelo
caminho mais previsível; "Y2K cromado" traz forma, cor e vocabulário próprios.

Especificidade sozinha não basta: o sinal também precisa ser do **território
certo**. Uma versão anterior trazia ladrilho hidráulico, terrazzo e art déco —
estéticas específicas, mas de arquitetura e decoração, com públicos de 25 a 40
anos. Ninguém compra capinha porque gostou de um piso. O critério de entrada
está escrito no `config.yaml`: cultura jovem, público de 16 a 32, e algo que a
pessoa carregaria no bolso o dia inteiro.

São 14 sinais e 3 produtos, 42 combinações.

### 2. Criação — texto e arte, ao mesmo tempo

Duas chamadas de IA disparam em paralelo, porque partem do mesmo insumo:

- **Texto** — gancho, legenda, call to action e hashtags, com voz de marca
- **Arte** — o desenho que vai impresso na capinha, em vetor

O texto passa por uma verificação de marca antes de seguir. Se violar uma regra
(preço, prazo de entrega, comparação com concorrente, superlativo sem lastro,
saúde/política/religião), a execução para em vez de publicar.

### 3. Composição — a arte vira produto

A arte é recortada na silhueta da capinha, com módulo de câmera, borda, sombra
projetada e brilho especular. Isso é feito por código, não por IA: garante que
a capinha do vídeo é exatamente a que a fábrica produziria.

### 4. Vídeo — o formato que a plataforma exige

Aproximação lenta sobre o produto, texto sobreposto e assinatura de marca no
encerramento. Saída em 1080×1920, H.264, yuv420p, 30 fps, com faixa de áudio.

O texto respeita a faixa inferior que a interface do TikTok cobre com nome de
perfil e legenda.

### 5. Publicação — com conformidade explícita

Envia ao TikTok com os campos que a plataforma exige, incluindo a divulgação de
que o conteúdo foi gerado por IA e a natureza comercial do post.

### 6. Confirmação — o resultado real

Publicar é assíncrono. A criação do post retorna sucesso antes de a plataforma
processar a mídia. O sistema acompanha o estado até o desfecho e traduz recusas
em instruções acionáveis.

---

## Quem faz o quê

### Infraestrutura

| Tecnologia | Papel |
|---|---|
| **Fly.io** | Hospeda a API em microVM, lendo `fly.toml`. Dois vCPUs dedicados e 4 GB. Desliga sozinha entre execuções e acorda na primeira requisição. Cobrança por segundo de execução. |
| **Docker** | Empacota a aplicação. Imagem `python:3.12-slim` sem nenhum `apt-get`: FFmpeg e o rasterizador de PDF chegam como binário dentro dos pacotes pip. |
| **FastAPI** | Define a API HTTP: rotas, validação de entrada, documentação interativa automática em `/docs`. |
| **uvicorn** | Servidor que executa a aplicação. |
| **Pydantic** | Valida o corpo das requisições e descreve cada campo na documentação. |
| **GitHub** | Versionamento e origem do deploy. |

### Orquestração

| Tecnologia | Papel |
|---|---|
| **Google Trends** | Fonte de tendências reais, pelo feed público. Sem chave, sem SDK, sem raspagem. Preferido ao `pytrends`, que raspa e quebra. |
| **n8n** | Orquestra o fluxo: dispara o trabalho, acorda o serviço, consulta o estado em laço, ramifica entre sucesso e falha e monta o relatório. Ferramenta low-code, sem código no fluxo. |
| **HTTP Request node** | Faz as chamadas à API. Não existe nó nativo de TikTok no n8n — o único da comunidade está marcado pelo próprio autor como não funcional. |

### Inteligência artificial

| Tecnologia | Papel |
|---|---|
| **Claude (Anthropic)** | Faz a **triagem das tendências**: decide o que pode virar estampa e recusa política, tragédia, pessoa real e marca de terceiro, com o motivo de cada recusa. |
| **Claude (Anthropic)** | Escreve o conteúdo — gancho, legenda, CTA, hashtags — com a voz da marca e as proibições do catálogo. Formato garantido por JSON Schema, não por instrução no prompt. |
| **Claude (Anthropic)** | Desenha a arte da capinha em **SVG**, a partir da tendência, do público e do produto. Escolhe a paleta pelo tema e declara o conceito visual antes de desenhar. |
| **Google Gemini** | Caminho preferencial para a arte quando há cota: gerador de imagem, com maior alcance visual (textura, pintura, grão). Opcional. |
| **Google Veo** | Caminho preferencial para o movimento do vídeo quando há cota. Opcional e desligado por padrão, por custo. |

### Geração de mídia

| Tecnologia | Papel |
|---|---|
| **svglib + reportlab** | Convertem o SVG da arte em PDF vetorial. Python puro. |
| **pypdfium2** | Rasteriza o PDF em PNG na resolução da área de impressão. Binário embutido no pacote. |
| **Pillow** | Compõe a arte na capinha em escala dobrada e reduz com LANCZOS, desenha a camada de texto, recorta a margem transparente do logotipo e produz a arte de reserva. |
| **FFmpeg** (via `imageio-ffmpeg`) | Monta o vídeo final: movimento, sobreposição de texto, encerramento com a marca, faixa de áudio e normalização para a especificação do TikTok. Binário embutido no pacote. |

Nem FFmpeg nem o rasterizador exigem instalação no sistema operacional: ambos
vêm como binário dentro do pacote `pip`. A decisão existe porque o ambiente de
hospedagem não tem gerenciador de pacotes do sistema.

### Publicação

| Tecnologia | Papel |
|---|---|
| **Zernio** | Transporte de publicação. Cliente auditado da Content Posting API oficial do TikTok. Hospeda a mídia, autentica a conta por OAuth e entrega o post. |
| **TikTok Content Posting API** | Destino final. Recebe o vídeo, processa e publica. |

### Configuração e dados

| Tecnologia | Papel |
|---|---|
| **PyYAML** | Lê `config.yaml`, onde vivem marca, catálogo, sinais, especificação do vídeo e parâmetros de publicação. |
| **python-dotenv** | Carrega credenciais do ambiente. Nenhuma chave em arquivo versionado. |
| **httpx** | Cliente HTTP das integrações. |

---

## Resultado medido

Execução real, conta de teste, publicação pública, sem intervenção manual:

| Métrica | Valor |
|---|---|
| Tempo total, da tendência à confirmação | **82 s** no serviço publicado |
| Tempo para acordar o serviço parado | 5,6 s |
| Tendências lidas e triadas | 10 lidas · 10 recusadas · tema veio do catálogo |
| Custo por execução | ~US$ 0,05 em IA · ~US$ 0,002 em processamento |
| Pico de memória no container | 360 MB, contra um teto de 4096 MB |
| Vídeo entregue | 1080×1920, H.264 yuv420p, 30 fps, faixa AAC, 8,00 s |
| Tamanho do arquivo | 0,7 a 0,9 MB, contra um teto de 25 MB |
| Estado final | `published` |
| Intervenção humana | nenhuma |

Custo por etapa, medido no ambiente publicado, com a mesma automação nas duas
hospedagens:

| Etapa | plano gratuito anterior (0,1 CPU) | Fly `performance-2x` |
|---|---|---|
| Radar: leitura e triagem | — | 7,7 s |
| Texto e arte (em paralelo) | 19,1 s | 34,8 s |
| Composição no produto | 3,4 s | 2,6 s |
| **Vídeo** | **135,1 s** | **12,7 s** |
| Publicação e confirmação | 18,6 s | 24,9 s |
| **Total** | **176,2 s** | **82,5 s** |

O vídeo ficou **11 vezes mais rápido** e passou de 77% para 15% do tempo total.
O que domina agora são as chamadas de IA e a latência da plataforma — coisas que
nenhuma hospedagem move.

A etapa de publicação é a mais instável de todas: cinco execuções mediram 18,6 s,
24,9 s, 29,9 s, 48,9 s e 92,4 s. A variação é do processamento do TikTok, não do
código — o sistema fica em laço aguardando o estado final. **Na prática, uma
execução leva de 1,5 a 3 minutos**, e o campo `tempos` do relatório mostra em
qual etapa o tempo foi gasto.

Duas linhas subiram de propósito, e vale dizer por quê. O radar são 7,7 s que
não existiam: é o preço de ler o mundo em vez de um arquivo. E a arte passou de
23,6 s para 34,8 s ao ganhar densidade mínima, planejamento de composição antes
do desenho e teto de tokens maior. **A automação ficou 18 s mais lenta e o
produto ficou melhor** — troca aceita conscientemente, com o número na mesa.

Vale registrar a previsão feita antes da migração: **~48 s totais, com o vídeo
em ~8 s.** O vídeo saiu em 10,2 s na primeira medição, perto. O total saiu em
64,4 s, longe — porque a estimativa tratou as etapas de rede como constantes, e
elas não são. A parte que dependia de hardware era previsível; a que dependia de
terceiros, não.

O relatório de cada execução traz esses tempos no campo `tempos`. A duração caiu
de 305 s para 176 s por medição dentro do ambiente antigo, e de 176 s para 64 s
pela troca de hospedagem — as duas vezes contrariando a primeira hipótese. Depois
subiu para 82 s ao ganhar o radar e a arte densa, e esse número está aqui porque
regressão de tempo escondida é pior que regressão de tempo declarada.

### Evidência

A confirmação não veio do log do próprio sistema. Numa das execuções em modo de
revisão, o aplicativo do TikTok notificou a conta com *"Seu conteúdo está pronto
— Edite seu vídeo antes de compartilhar"*. O vídeo saiu do código, foi
hospedado, foi buscado pela plataforma, passou pelo processamento dela e chegou
ao criador.

Em publicação direta, o estado atravessa `publishing` por cerca de 20 segundos
antes de virar `published` — latência real do processamento do TikTok, e a razão
de o sistema acompanhar em vez de disparar e esquecer.

---

## Decisões de arquitetura

### Por que a hospedagem mudou

A automação nasceu num plano gratuito de preço fixo e funcionava. O que a
instrumentação revelou foi que ela funcionava **contra** a plataforma:

| | plano gratuito anterior |
|---|---|
| CPU | 0,1 de um núcleo, permanente |
| Memória | 512 MB |
| Cobrança | mensal, independente de uso |
| Tempo de vídeo | 135,1 s |

O teto de 512 MB obrigou a codificar com uma thread, sem quadros B e com
referência única. Essa economia era necessária — mas amarrava a velocidade,
porque memória e tempo puxavam para lados opostos e memória vencia por ser
fatal. O serviço passava 23h55 por dia ocioso pagando por capacidade que não
usava, e os 5 minutos em que trabalhava eram justamente os que faltava.

**A carga é em rajada.** Poucos minutos de trabalho pesado, horas de silêncio.
Um plano de preço fixo é o formato errado para esse perfil: cobra pelo tempo
ocioso e limita o tempo ativo.

O Fly cobra **por segundo e não cobra CPU nem RAM de máquina parada**. Isso
inverte a economia:

| | plano gratuito anterior | plano pago equivalente | **Fly `performance-2x`** |
|---|---|---|---|
| CPU | 0,1 fixo | 0,5 fixo | **2 dedicados** |
| Memória | 512 MB | 512 MB | **4 GB** |
| Custo/mês | US$ 0 | US$ 7,00 | **~US$ 0,50** |
| Acordar do repouso | ~50 s | não dorme | **5,6 s** |
| Execução completa | 176,2 s | — | **64,4 s** |

Os tempos da última linha são os da migração, quando as duas hospedagens rodavam
exatamente o mesmo código — é o que torna a comparação honesta. A automação hoje
leva 82 s, porque ganhou o radar e uma arte mais densa depois disso.

O plano pago de preço fixo custaria **14 vezes mais por um quarto da CPU**. A
comparação acima é a justificativa da escolha e fica registrada como histórico;
a hospedagem anterior não é mais uma alternativa mantida, e o repositório não
guarda configuração para ela.

Uma execução de 90 s em `performance-2x` custa US$ 0,002. Trinta execuções por
mês somam cinco centavos de processamento; o custo passa a ser o disco da
máquina parada, não o trabalho. **Um núcleo dedicado sai mais barato que meio
núcleo fixo, porque não se paga pelas horas de silêncio.**

#### A armadilha das máquinas compartilhadas

A escolha óbvia seria `shared-cpu-1x`, que anuncia "1 vCPU". Ela renderia **5 ms
a cada 80 ms — 6,25% de um núcleo**, menos que o plano gratuito que estava sendo
abandonado. Passar disso exige gastar um saldo de rajada acumulado, e a
documentação não informa a taxa de recomposição desse saldo.

Codificar vídeo é carga sustentada de CPU: o saldo acabaria no meio. A troca
teria saído **mais lenta** que a origem. Daí `performance-2x`, com núcleos sem
cota.

#### O que a mudança destravou no código

O orçamento de codificação deixou de ser constante e passa a ser lido do
ambiente, em `src/video.py`. A cota vem do cgroup, não de `os.cpu_count()` —
esta última reporta os núcleos do hospedeiro, e no plano gratuito anterior dizia
haver vários enquanto a fatia real era 0,1.

Com folga de memória, o perfil enxuto dá lugar a `ref=3` e `bframes=2`: **28% de
redução no arquivo pelo mesmo tempo de parede** (1293 KB → 936 KB). A mesma
imagem, menos bytes.

Uma tentativa foi descartada por medição: subir o preset de `veryfast` para
`medium` junto com a memória parecia natural e saiu **45% mais lento com arquivo
maior** (7,1 s / 1048 KB contra 4,9 s / 937 KB). O conteúdo é uma aproximação
lenta sobre arte vetorial chapada — a busca de movimento cara do `medium` não
tem o que encontrar. O preset ficou onde estava.

Fica registrado o que a troca **não** resolve: as etapas de IA e de publicação
respondem por praticamente todo o tempo restante, e variam conforme os
provedores. Esse é o piso da automação, e nenhuma hospedagem o move.

#### O deploy sai do CLI, não do painel

Os dois primeiros deploys subiram quebrados, com o proxy sem máquina para
rotear. O log foi direto ao ponto:

```
Preparing to run: `/app/.venv/bin/fastapi run` as root
To use the fastapi command, please install "fastapi[standard]":
machine has reached its max restart count of 10
```

O detector automático da plataforma escaneou o repositório antes de existir um
`Dockerfile` aqui e gerou o dele, com dois defeitos somados: o executável
`fastapi` vem do pacote `fastapi-cli`, instalado só com `fastapi[standard]`, e
este projeto declara `fastapi` puro; e `fastapi run` escuta na porta 8000,
enquanto o proxy encaminha para a 8080.

O detalhe que transforma isso em armadilha: **a integração com o GitHub guarda a
configuração gerada do lado da plataforma e não lê a do repositório.** O painel
oferece um botão para mesclar os arquivos gerados, mas esse ramo foi cortado do
estado anterior à migração — mesclá-lo removeria 268 linhas, incluindo o
orçamento de codificação adaptativo. Usar a configuração correta e preservar o
código eram objetivos incompatíveis por aquele caminho.

A saída é implantar pelo CLI, que lê o `fly.toml` e o `Dockerfile` do
repositório. Foi o mesmo deploy que corrigiu o segundo sintoma: as máquinas
tinham sido criadas como `shared-cpu-1x` com 256 MB — a configuração gerada
trazia exatamente a armadilha descrita acima, e um deploy pelo painel troca a
imagem sem redimensionar a máquina.

### Por que a IA gera a arte, não o vídeo inteiro

Pedir a um modelo de vídeo *"uma capinha da GoCase com arte retrô dos anos 90"*
devolve um celular genérico, com arte aproximada e texto ilegível. Modelos de
vídeo não renderizam produto específico com fidelidade — e, mais importante,
**um clipe de vídeo não é imprimível.**

O que a GoCase vende é a arte. Então a arte é o que a IA gera, na proporção real
da área de impressão do produto — alta, cerca de 1:2, não quadrada. A composição
no produto é feita por código, garantindo fidelidade.

Resultado: **cada execução produz um ativo de negócio reutilizável**, não só um
post descartável. O arquivo `.svg` fica salvo ao lado do `.png` — vetor escala
sem perda e separa cores para impressão, que é o formato certo para produção sob
demanda.

### Por que não a API oficial do TikTok diretamente

A Content Posting API existe e funciona, mas tem **dois portões distintos**:

| Portão | O que libera |
|---|---|
| **App Review** | tira o app do sandbox |
| **Audit** | tira a restrição de visibilidade |

Enquanto o cliente de API **não é auditado**, a documentação oficial é
explícita: todo post sai em `SELF_ONLY`, a conta precisa estar privada no
momento da publicação, e o limite é de 5 usuários por 24 horas. O post existe, e
ninguém além do dono o vê.

A auditoria exige uma **interface inspecionável**: tela de publicação com avatar
e nome do criador, seletor de privacidade, toggles de Duet, Stitch e
comentários, e divulgação de conteúdo comercial. Um fluxo headless não tem
interface a auditar. **Não é questão de prazo — é inaprovável por definição.**

A solução legítima é o modelo de parceiro desenhado pela própria plataforma: um
cliente já auditado atua como transporte, e a conta é autorizada pela tela de
autorização do `tiktok.com` — nunca entregando senha a terceiro.

A escolha do transporte foi decidida por teste, não por marketing: a
recomendação inicial era outro serviço, com nó n8n oficial. O teste de aceitação
— conectar a conta e publicar manualmente, conferindo se o post sai público —
inverteu a decisão.

### Conformidade não é opcional

| Campo | Valor | Por quê |
|---|---|---|
| `video_made_with_ai` | `true` | O conteúdo é gerado por IA. Exigência de política. |
| `commercialContentType` | `brand_organic` | Promoção do próprio negócio, não parceria paga. |
| `content_preview_confirmed` | `true` | Exigência legal da plataforma. |
| `express_consent_given` | `true` | Exigência legal da plataforma. |

### Guardrails de marca verificados por código

As proibições vivem no `config.yaml` e entram no prompt **e** são conferidas
depois da geração. Se o texto violar uma regra, o pipeline barra em vez de
publicar.

O motivo: **modelo de linguagem é bom em seguir instrução, mas não é mecanismo
de garantia.** A verificação normaliza acentos antes de comparar — sem isso
*"revolucionária"* seria barrado e *"revolucionaria"* passaria, e um modelo
produz as duas formas.

O formato da resposta também não é pedido por prompt: é imposto pela API via
JSON Schema. Pedir "responda em JSON" e torcer é o modo mais comum de quebrar
pipeline em produção.

### Por que jobs assíncronos

A geração leva minutos. Nenhum request HTTP síncrono sobrevive a isso — nem no
n8n, nem em plano gratuito, nem em proxy nenhum. O fluxo dispara, recebe um
`job_id` e consulta até o estado final.

O polling tem um efeito colateral útil, e ele virou requisito: a máquina desliga
sozinha quando não há tráfego, e o job roda em thread de fundo, que o proxy não
enxerga. É a consulta a cada poucos segundos que mantém a máquina de pé até o
fim do trabalho. O `kill_timeout` de 5 minutos no `fly.toml` é a rede de
segurança para o caso de o tráfego cessar antes da hora.

---

## Degradação graciosa

A arte tem três caminhos, tentados em ordem:

| # | Caminho | O que entrega | `etapas.arte` |
|---|---|---|---|
| 1 | Gerador de imagem | maior alcance visual: textura, pintura, grão | `imagem_ia` |
| 2 | Vetor desenhado pela IA de texto | acerta o tema; escala sem perda e separa cores | `vetor_ia` |
| 3 | Composição geométrica local | sempre disponível, na paleta da marca | `local` |

O vídeo tem dois: animação por IA sobre o mockup, ou aproximação lenta em
FFmpeg.

**Isto não é hipótese.** O plano gratuito do provedor de imagem concede
`limit: 0` para geração de imagem e de vídeo — cota inexistente, não limite por
minuto. O pipeline caiu para o caminho 2 sozinho, e é ele que produz o material
das execuções registradas aqui.

O logotipo do encerramento segue a mesma regra: ausente, o vídeo é montado sem
assinatura e o relatório registra `logo: ausente`. Ativo decorativo não derruba
publicação.

Efeito colateral do desenho: **a suíte de testes roda sem nenhuma credencial.**

---

## Armadilhas de plataforma tratadas no código

Quase todos os itens vieram da documentação do fornecedor, antes de quebrarem.
As exceções estão marcadas.

| Armadilha | Tratamento |
|---|---|
| Ferramentas de workflow reusam `x-request-id`; chamadas seguintes devolvem o post da primeira, silenciosamente | UUID novo por chamada |
| Conteúdo idêntico na mesma conta em 24h retorna HTTP 409 | O seletor evita combinações recentes e registra histórico |
| Níveis de privacidade variam por criador; usar um inválido faz o post falhar | Consulta `creator-info` antes e rebaixa para uma opção permitida |
| ~13% de falha de publicação na plataforma | Polling até o estado final; nunca fire-and-forget |
| Upload direto recusa acima de 25 MB | Verificação antes do envio e recompressão automática |
| Serviços de nuvem de arquivos devolvem HTML, não vídeo | A mídia é hospedada pelo próprio transporte |
| Vídeo sem faixa de áudio processa de forma menos confiável | Faixa silenciosa injetada quando a origem não tem áudio |
| Conta pode estar no limite diário sem que a publicação avise | `canPostMore` é consultado antes; 429 vira mensagem legível |
| Conta conectada mas com token morto falha tarde e mal | Contas com `needsReconnection` são descartadas na descoberta |
| Conteúdo de parceria paga é recusado com visibilidade privada | Combinação inválida é barrada antes do envio |
| **Descoberta em produção:** máximo de 5 rascunhos pendentes por conta em 24h — e a consulta de capacidade reporta que a conta pode postar, porque mede a cota de publicação e não a de rascunhos | Erro traduzido em instrução acionável |
| **Descoberta em produção:** jobs vivem em memória e somem se o serviço reiniciar | O fluxo n8n tolera 404 na consulta e ramifica para falha tratada |

---

## Configuração sem código

Tudo que um time de marketing ajustaria vive no `config.yaml`, fora do código:

- **Voz e paleta da marca** — governam o vídeo (texto, chamada, assinatura). A
  arte impressa segue a paleta do tema, não a da marca
- **Proibições** — a lista que os guardrails verificam
- **Catálogo de produtos** — SKU, nome, linha e área de impressão real
- **Sinais de tendência** — tema, público e linguagem visual de cada gatilho
- **Especificação do vídeo** — resolução, duração, taxa de quadros
- **Parâmetros de publicação** — privacidade, comentários, Duet, Stitch
- **Interruptores de custo** — geração de imagem e de vídeo por IA, separados

Configuração ausente ou inválida não derruba nada: o sistema avisa e usa os
padrões embutidos. Credenciais nunca ficam em arquivo versionado — só em
variáveis de ambiente.

### Controle de custo

Geração de imagem e de vídeo por IA têm preços muito diferentes — vídeo custa
cerca de 30 vezes mais por execução. Cada uma tem seu próprio interruptor, e o
vídeo vem desligado. Habilitar faturamento no provedor não deve abrir as duas
torneiras sem alguém escolher.

---

## Arquitetura do código

Responsabilidade única por módulo:

| Módulo | Responsabilidade |
|---|---|
| `src/radar.py` | Lê tendências reais e faz a triagem; recusa mais do que aprova |
| `src/tendencia.py` | Seleciona sinal e produto; evita repetir combinações |
| `src/criativo.py` | IA de texto com schema imposto; verifica guardrails de marca |
| `src/arte.py` | Gera a arte imprimível; três caminhos; rasteriza o vetor |
| `src/mockup.py` | Compõe a arte na capinha; garante fidelidade de produto |
| `src/video.py` | Monta o vídeo e normaliza para a especificação do TikTok |
| `src/publicador.py` | Publica e confirma; trata as armadilhas da plataforma |
| `src/agente.py` | `executar_pipeline`: o fluxo completo, em uma função só |
| `src/config.py` | Carrega `config.yaml` com fallback embutido |
| `api.py` | Superfície HTTP com jobs assíncronos |
| `main.py` | Execução por terminal |

**Fonte única de verdade.** O fluxo vive em `executar_pipeline`; a API HTTP, o
terminal e os testes chamam a mesma função. Nenhum reimplementa etapa.

---

## Qualidade

`testar.py` executa **65 verificações** sem exigir credencial: carga e
degradação da configuração, rotação de tendências, triagem do radar com a fonte
fora do ar, guardrails caso a caso, saneamento do SVG vindo da IA, cobertura de
acentos da fonte do vídeo, pipeline de mídia completo com conferência da
especificação real do arquivo, integridade do fluxo n8n, interpretação das
respostas da API de publicação, área segura do texto e comportamento das
superfícies quando falta chave.

Três blocos nasceram de defeitos que chegaram a produção: a fonte sem acentos, o
SVG com cor partida por espaço e a triagem do radar. Teste escrito depois do
defeito não impede aquele defeito — impede a volta dele.

Defeitos reais encontrados durante a construção, agrupados por **como** foram
descobertos — cada método pegou o que os outros não alcançavam:

| Método | Defeitos encontrados |
|---|---|
| **Revisão de documentação** | níveis de privacidade lidos como texto quando a API devolve objetos; dois conceitos distintos de "rascunho" tratados como um só |
| **Inspeção visual do material** | paleta escapando da identidade; contraste insuficiente escondendo texto; sombra desenhada como moldura sólida; texto sobre a arte |
| **Uso repetido em condição real** | limite de rascunhos pendentes; jobs perdidos em reinício de serviço |
| **Medição instrumentada** | consumo de memória e custo por estágio |

### Memória: 1011 MB → 193 MB

O serviço morria por estouro no container de 512 MB. Medir por estágio mostrou
que arte e composição somavam menos de 110 MB e o FFmpeg sozinho usava 1011 MB.

| Causa | Efeito |
|---|---|
| `-threads` do FFmpeg não controla o threading interno do libx264 — é preciso `threads=1` dentro de `-x264-params` | 906 → 336 MB |
| `-loop 1` numa entrada de imagem bufferiza ~150 MB por arquivo; repetir o quadro dentro do grafo de filtros custa 8 MB | 394 → 199 MB |
| O pipeline codificava duas vezes: gerava um MP4 intermediário e o relia para aplicar o texto | 448 → 307 MB |

Pico ao fim daquela investigação: **193 MB**, contra o teto de 512 MB da
hospedagem da época.

Hoje o pico é **360 MB**, e o aumento foi deliberado: a composição do produto
passou a ser desenhada em escala dobrada e reduzida com LANCZOS, o que
quadruplica os pixels em memória e elimina o serrilhado das quinas. Contra o
teto atual de 4096 MB, é troco — mas teria sido impossível no teto antigo.

Os dois números medem o mesmo processo em momentos diferentes: **193 MB** é onde
a otimização chegou sob restrição de 512 MB; **360 MB** é onde ele está depois de
gastar parte da folga nova em qualidade de imagem.

Vale o registro de método: a primeira hipótese estava errada em dois momentos
distintos. Reduzir o buffer do zoom custava 6 MB. E as quedas do serviço que
pareciam falta de memória eram, na verdade, redeploys disparados durante a
própria execução — o que só ficou claro quando o serviço passou a reportar o
próprio consumo.

O desfecho desta investigação: com 4 GB disponíveis, o teto de 512 MB deixou de
existir e a economia toda deixou de ser obrigatória. Ela continua no código como
piso, selecionada automaticamente quando o ambiente é apertado — a automação
roda nos dois mundos sem editar nada.

---

## Escopo e evolução

### Limitações conhecidas

**Áudio.** Não existe API de música licenciada — nem oficial da plataforma, nem
por intermediário. O que faz um vídeo circular no TikTok é usar um som em alta,
e isso só o aplicativo oferece. O vídeo sai com faixa silenciosa.

Existe um modo alternativo que entrega ao Creator Inbox, onde um humano finaliza
pelo aplicativo e escolhe o som. Ele não é o padrão porque a plataforma aceita
no máximo 5 rascunhos pendentes por conta em 24 horas e não oferece forma de
limpá-los pela API — uma rodada de testes trava a conta.

**Alcance do radar.** A fonte é o Google Trends, que mede *busca* — não moda
visual. Tendência estética costuma nascer no TikTok e no Pinterest antes de
virar busca no Google, e nenhuma das duas expõe esses dados publicamente. Na
prática a triagem recusa quase tudo, e é o catálogo curado que sustenta a
operação. O radar entrega auditoria e o caminho para uma fonte melhor, não um
fluxo constante de temas.

**Autenticação.** A API sobe sem autenticação, por decisão de escopo do business
case. Antes de operar com a conta real da marca, exige chave de acesso.

**Auditoria.** Uma implementação direta contra a API oficial exigiria construir
a interface de publicação que a auditoria requer — o que muda a natureza do
projeto, de automação para produto.

### Evolução natural

- Ampliar as fontes do radar para além do Google Trends — o Creative Center do
  TikTok e o Pinterest capturam moda visual antes de ela virar busca, que é
  onde a triagem hoje encontra pouco
- Realimentar o desempenho dos posts para priorizar os temas que converteram,
  fechando o ciclo entre publicação e decisão
- Ligar a arte aprovada direto na fila de produção, fechando o ciclo até a
  fábrica
- Teste A/B de gancho sobre a mesma arte, reaproveitando o ativo caro
