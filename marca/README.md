# Ativos de marca

Logotipo exibido no encerramento do vídeo, em fade sobre um véu claro, com o
produto visível por trás.

| Arquivo | Uso |
|---|---|
| `gocase.png` | azul — o padrão, para o véu claro |
| `gocase-branco.png` | branco — para um véu escuro, se a paleta mudar |

Qual será usado vem de `marca.logo` no `config.yaml`.

Os arquivos vêm num quadrado de 1080x1080 com cerca de 96% de área transparente.
O pipeline recorta a margem vazia antes de escalar: sem isso a escala valeria
para a moldura e o wordmark sairia minúsculo.

Sem o arquivo, o vídeo é montado sem assinatura e o relatório registra
`logo: ausente` — ativo decorativo não derruba publicação.
