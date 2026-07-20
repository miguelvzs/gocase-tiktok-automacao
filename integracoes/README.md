# Integração — n8n e API HTTP

O fluxo n8n é a orquestração; o serviço Python faz o trabalho. Esta separação
existe por um motivo concreto: a geração de vídeo leva de 1 a 3 minutos, e
nenhum request HTTP síncrono sobrevive a isso. O contrato é assíncrono.

---

## O fluxo

[`radar-tendencia-gocase.json`](radar-tendencia-gocase.json) — importe uma vez
pelo menu **Import from File** do n8n.

```
Disparo manual ─┐
                ├─→ Configuração ─→ Dispara o job ─→ Aguarda ─→ Consulta o estado
Todo dia às 10h ┘                                       ↑              │
                                                        │              ↓
                                                        └──── Ainda executando?
                                                                       │ não
                                                                       ↓
                                                                  Deu certo?
                                                                   ↙        ↘
                                                    Relatório de execução  Falha tratada
```

**Nada a ajustar para rodar.** O campo `api_url` do nó *Configuração* já aponta
para o serviço publicado. Não há credencial embutida nem caminho de disco, então
o arquivo importa em qualquer máquina e funciona de imediato. Só troque `api_url`
se rodar o serviço em outro lugar.

Os outros campos do nó *Configuração*:

| Campo | Efeito |
|---|---|
| `sinal_id` | Vazio: o sistema escolhe uma tendência ainda não usada. Preenchido: fixa a tendência. |
| `sku` | Vazio: o sistema escolhe o produto. Preenchido: fixa o produto. |
| `publicar` | `false` envia para o Creator Inbox da TikTok — a mídia atravessa a integração inteira sem nada ficar público. `true` vai ao ar no perfil. |

O gatilho agendado vem desabilitado de propósito. A TikTok impõe um limite
diário de posts por API, por conta — ligar o agendamento sem calibrar a
frequência queima a cota.

---

## Por que HTTP Request e não um nó de TikTok

Não existe nó nativo de TikTok no n8n. O único nó da comunidade
([`@igabm/n8n-nodes-tiktok`](https://github.com/igabm/n8n-nodes-tiktok)) está
marcado pelo próprio autor como *"Work In Progress — Not Working Yet"*.

O vídeo de referência do desafio resolve o mesmo problema do mesmo jeito: usa
um HTTP Request node para a Perplexity porque não havia nó nativo. É o padrão
estabelecido pela própria referência, não um contorno.

---

## Contrato da API

Base: `https://radar-tendencia-gocase.onrender.com`. Tudo é HTTP + JSON, sem SDK.

### `POST /publicar`

Aceita o pedido e devolve imediatamente. **Não bloqueia.**

```json
{ "sinal_id": null, "sku": null, "rascunho": true }
```

Resposta `202`:

```json
{ "job_id": "b7c1…", "consultar": "/jobs/b7c1…" }
```

### `GET /jobs/{job_id}`

Estado corrente. Enquanto executa, `etapa` diz onde está — útil para exibir
progresso em vez de uma barra parada.

```json
{
  "job_id": "b7c1…",
  "estado": "executando",
  "etapa": "video",
  "mensagem": "Montando o vídeo vertical"
}
```

Concluído:

```json
{
  "estado": "concluido",
  "relatorio": {
    "produto": { "sku": "CASE-IPH-15P", "nome": "Capinha iPhone 15 Pro" },
    "sinal": { "id": "inverno-retro", "tema": "estética retrô anos 90…" },
    "criativo": { "gancho": "…", "legenda": "…", "hashtags": ["…"] },
    "etapas": { "arte": "ia", "video": "local" },
    "estado": "published",
    "destino": "creator_inbox",
    "url_perfil": "https://tiktok.com/@…",
    "video_mb": 1.01,
    "segundos": 190.3
  }
}
```

`url_publica` traz o link direto do post quando a TikTok o devolve. Ela
frequentemente devolve esse campo vazio mesmo com status `published`; nesse
caso o relatório traz `url_perfil` no lugar, para que o operador ache o post em
vez de receber "publicado" e nenhuma forma de conferir.

Falhou:

```json
{ "estado": "falhou", "etapa": "publicacao", "erro": "…", "tipo_erro": "ErroPublicacao" }
```

O campo `etapa` sobrevive à falha — dá para saber se quebrou na redação, na
geração da arte, no vídeo, no upload ou na publicação.

### `GET /jobs/{job_id}/video`

Baixa o MP4 gerado. Útil para conferir o material antes de publicar.

### `GET /catalogo`

Sinais e produtos disponíveis. Existe para que o n8n monte listas de opção sem
duplicar o `config.yaml` — fonte única de verdade.

### `GET /`

Saúde do serviço e número de jobs ativos.

---

## Estados possíveis de `relatorio.estado`

| Estado | Significado |
|---|---|
| `published` | A TikTok confirmou o recebimento. Combine com `destino` para saber onde foi parar. |
| `partial` | A TikTok aceitou parcialmente — confira o post. |
| `criado` | Post criado no Zernio, sem `post_id` para acompanhar. |
| `indeterminado` | O post existe, mas o status não concluiu no tempo do polling. **Não republique** — confira o painel do Zernio antes, para não duplicar. |

E `relatorio.destino` diz o alvo pretendido:

| Destino | Significado |
|---|---|
| `creator_inbox` | Foi para a caixa de entrada do criador na TikTok. O vídeo está na plataforma; alguém finaliza pelo aplicativo. |
| `publicado` | Foi direto para o perfil, público. |

A distinção importa porque os dois modos usam caminhos diferentes da API da
TikTok — `post_mode: MEDIA_UPLOAD` para o inbox, `DIRECT_POST` para o perfil —
e escopos OAuth diferentes (`video.upload` contra `video.publish`).

---

## Consumindo sem n8n

Por ser HTTP puro, Make, Power Automate, um cron com `curl` ou código próprio
consomem o mesmo contrato. O n8n é o caminho documentado e testado por ser o
padrão na GoCase.

```bash
JOB=$(curl -s -X POST "$API/publicar" -H 'Content-Type: application/json' \
      -d '{"rascunho": true}' | python -c "import sys,json;print(json.load(sys.stdin)['job_id'])")

until curl -s "$API/jobs/$JOB" | grep -q '"estado": *"\(concluido\|falhou\)"'; do sleep 15; done
curl -s "$API/jobs/$JOB"
```
