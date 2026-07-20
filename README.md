# Radar de Tendência — GoCase

Automação que transforma **um sinal de tendência em uma capinha publicada no
TikTok**, sem intervenção humana: escolhe o tema, cria a arte, compõe o produto,
monta o vídeo vertical e publica — com a divulgação de conteúdo gerado por IA
que a plataforma exige.

Business case para o processo seletivo de Estágio em RPA na **GoCase (GoGroup)**.
Área de negócio: Marketing e Aquisição.

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

O operador abre o fluxo no n8n e clica em executar. Ou habilita o gatilho
agendado e não abre mais.

---

## Por que a IA gera a **arte**, não o vídeo inteiro

Esta é a decisão de arquitetura central do projeto.

Pedir a um modelo de vídeo *"uma capinha da GoCase com arte retrô dos anos 90"*
devolve um celular genérico, com arte aproximada e texto ilegível. Modelos de
vídeo não renderizam produto específico com fidelidade — e, mais importante,
**um clipe de vídeo não é imprimível.**

O que a GoCase vende é a arte. Então a arte é o que a IA gera, num arquivo
quadrado na resolução da área de impressão. A composição no produto é feita por
código, o que garante que a capinha do vídeo é exatamente a capinha que a
fábrica produziria. A IA só entra de novo para dar movimento ao mockup pronto.

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

Cada item aqui é documentado pelo fornecedor como causa real de falha em
produção. Nenhum foi descoberto quebrando.

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

| Estágio | Caminho principal | Reserva |
|---|---|---|
| Arte | modelo de imagem | composição geométrica na paleta da marca, derivada do conceito |
| Vídeo | animação por IA a partir do mockup | Ken Burns em FFmpeg sobre o mesmo mockup |

O caminho de reserva é código de produção, não simulação — e o relatório de
cada execução informa qual foi usado (`etapas.arte`, `etapas.video`). Cota
esgotada, chave ausente ou API instável não interrompem a operação; apenas
mudam a qualidade do movimento, com registro.

Como efeito colateral, **a suíte de testes roda sem nenhuma credencial**.

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

Python 3.12+ · Pillow (arte e composição) · FFmpeg via `imageio-ffmpeg`
(binário embutido, sem instalação de sistema) · FastAPI e uvicorn (API HTTP) ·
PyYAML (configuração externa) · Anthropic Claude (redação com schema imposto) ·
Google Gemini (imagem e vídeo, opcional) · Zernio (transporte de publicação) ·
n8n (orquestração low-code) · Render (hospedagem).

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

`testar.py` executa **35 verificações** sem exigir credencial: carga e
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

Os dois últimos merecem nota porque nenhum apareceria em teste que não olhasse o
formato de resposta. O primeiro rebaixaria toda publicação para um nível de
privacidade inválido. O segundo é mais sutil: o serviço de transporte tem um
rascunho próprio, que guarda o post no painel dele e **nunca chega à TikTok** —
enquanto a TikTok tem o Creator Inbox, que recebe a mídia de verdade. Tratar os
dois como sinônimos faria o modo de teste não exercitar justamente o caminho que
precisava ser testado.

Outras salvaguardas embutidas: geração de arte determinística (o mesmo conceito
produz o mesmo arquivo, o que torna uma execução reproduzível); jobs expiram
sozinhos em 1 hora; falha de publicação preserva a etapa onde parou; e status
indeterminado nunca dispara republicação automática, para não duplicar post.

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
