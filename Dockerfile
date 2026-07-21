# Imagem de execução no Fly.io.
#
# Não há `apt-get` aqui, e isso é intencional. FFmpeg vem como binário estático
# dentro do pacote `imageio-ffmpeg`, e o rasterizador de PDF vem dentro do
# `pypdfium2` — ambos via pip, ambos com wheel manylinux. A mesma decisão que
# permitia rodar no runtime Python do Render agora mantém esta imagem pequena.
#
# Tamanho importa em dinheiro: máquina parada não paga CPU nem RAM, mas paga
# disco a US$ 0,15 por GB a cada 30 dias. O disco é o maior custo fixo desta
# aplicação, então `slim` e `--no-cache-dir` não são detalhe estético.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# As dependências entram antes do código para que uma alteração em src/ não
# invalide a camada de instalação.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# A porta é fixa no contrato com o fly.toml, não herdada do ambiente: o Fly não
# injeta $PORT como o Render fazia.
#
# O arranque é `uvicorn`, não `fastapi run`. O detector automático do Fly gera
# `CMD ["/app/.venv/bin/fastapi", "run"]`, que falha por dois motivos ao mesmo
# tempo: o executável `fastapi` vem do pacote `fastapi-cli`, instalado só com
# `fastapi[standard]`, e este projeto declara `fastapi` puro; e `fastapi run`
# escuta na porta 8000, enquanto o proxy encaminha para a 8080. O container
# morria no arranque e o proxy não achava máquina para rotear.
EXPOSE 8080
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
