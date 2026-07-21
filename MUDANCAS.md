# Últimas mudanças

Registro das três frentes fechadas depois da primeira medição no ambiente
publicado. Documento curto de propósito: o detalhe técnico vive no README e nos
comentários do código.

---

## 1. O radar passou a ler o mundo

**O problema.** O projeto se chama Radar de Tendência e lia um arquivo YAML. É a
primeira pergunta que qualquer pessoa técnica faria, e a resposta honesta era
"ainda não varre nada".

**O que foi feito.** `src/radar.py` busca o que o Brasil está pesquisando agora
no feed público do Google Trends — endpoint oficial, sem chave, sem
dependência nova — e submete cada busca a uma triagem.

**O achado que definiu o desenho.** As dez altas do momento, numa leitura real:

```
8 de janeiro · deltan dallagnol · banco master · tribunal de contas
liga dos campeões · fenerbahçe · mg-188 · bianca andrade
balanço da copa · climatização
```

Política, processo judicial, notícia financeira, clube de futebol, nome de
pessoa e provável acidente rodoviário. **Nenhum vira estampa**, e vários violam
diretamente as proibições da marca. Um radar ingênuo teria tentado desenhar o 8
de janeiro.

Então a função principal da triagem não é aprovar — **é recusar**. Ela barra
política, tragédia, pessoa real, marca de terceiro, clube e notícia sem carga
visual. Aprova apenas o que é estético ou sazonal, tem forma própria, interessa
a quem tem de 16 a 32 anos e alguém carregaria no bolso. Na dúvida, recusa.

**Medido.** Contra a leitura real: 10 recusados, 0 aprovados, com o motivo de
cada um. Contra uma lista injetada com casos aprováveis: 3 aprovados e 4
recusados, e os aprovados vieram com o nome próprio removido — `são joão 2026`
virou "festa junina com bandeirinhas", `flamengo` foi barrado como propriedade
de marca.

**Consequência prática.** O catálogo curado continua sendo o caminho mais
frequente, e isso é correto, não um plano B. O relatório de cada execução passa
a registrar `etapas.origem_do_tema` (`radar` ou `catalogo`) e a lista de recusas
com o motivo.

**Custo.** Cerca de 11 s na frente do pipeline: leitura do feed mais uma chamada
de triagem com esforço baixo, que é classificação e não criação.

**Degradação.** Fonte fora do ar, feed vazio, triagem falhando ou credencial
ausente — todos devolvem lista vazia e o catálogo assume. Uma fonte externa
instável não pode derrubar a publicação.

---

## 2. O histórico sobrevive ao deploy

**O problema.** `historico.json` morava em `output/`, dentro da imagem. Isso
bastava enquanto o serviço era um processo de vida longa. No modelo atual a
máquina dorme entre execuções e é recriada a cada deploy, então a memória do que
já foi publicado zerava junto — e combinação repetida é recusada pela plataforma
como conteúdo duplicado dentro de 24 horas.

Foi um efeito colateral da mudança de hospedagem que só apareceu ao procurar
por ele.

**O que foi feito.** O caminho passa a sair da variável `DIRETORIO_DADOS`, que
no ambiente publicado aponta para um volume montado em `/dados`. Sem a variável,
cai em `output/` — quem roda `python main.py` na própria máquina não precisa
montar volume nenhum.

**Custo.** O volume mínimo de 1 GB custa US$ 0,15 por mês, para guardar poucos
kilobytes.

---

## 3. O serviço publicado estava oito commits atrás

**O problema.** `git push` não faz deploy. A integração com o GitHub foi
abandonada quando ficou claro que ela ignora o `fly.toml` do repositório, e
nenhum `fly deploy` foi disparado desde então.

Consequência medida antes da correção:

```
$ curl .../catalogo
sinais no ar: 5
['inverno-retro', 'volta-as-aulas', 'festa-junina', 'gamer-neon', 'botanico-minimal']
```

O serviço rodava os temas antigos, a paleta da marca imposta sobre a arte e **o
defeito que apagava os acentos do vídeo**. Quem abrisse a URL veria a versão
quebrada.

**O que foi feito.** Deploy pelo CLI e uma execução completa verificada. Os
números medidos estão no README.

---

## O que continua fora de escopo

- **Autenticação.** O serviço sobe sem chave de acesso, por decisão de escopo do
  business case. Operar com a conta real da marca exige esse passo antes.
- **Trilha sonora.** Não existe API de música licenciada, nem oficial nem por
  intermediário. O vídeo sai com faixa silenciosa.
- **Melhor-de-N na arte.** Gerar candidatos em paralelo e escolher atacaria a
  variância que resta. Custa cerca de 10 s no caminho crítico e depende de um
  critério de escolha que ainda não foi validado — testar o juiz contra
  candidatos já gerados vem antes de integrar.
