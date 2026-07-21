"""Seleção do sinal de tendência e do produto.

Espelha o "Google Sheets trigger" + "Code node to grab the latest media" do
vídeo de referência: a automação lê uma fonte de dados de produto e escolhe o
que publicar. Não inventa SKU.

A seleção precisa **variar entre execuções**. O Zernio rejeita conteúdo
duplicado na mesma conta dentro de 24 horas com HTTP 409, então repetir o mesmo
par (sinal, produto) faz a publicação falhar depois de todo o custo de geração.
"""

from __future__ import annotations

import json
import os
import logging
import random
from datetime import date
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent
# O histórico de combinações já usadas precisa sobreviver ao deploy.
#
# Ele morava em `output/`, dentro da imagem, o que funcionava enquanto o serviço
# era um processo de vida longa. Com máquina que dorme entre execuções e é
# recriada a cada publicação de versão, a memória zerava junto — e combinação
# repetida é recusada pela plataforma como conteúdo duplicado dentro de 24h.
#
# `DIRETORIO_DADOS` aponta para o volume montado no ambiente publicado. Sem a
# variável, cai em `output/`, que é o certo para a máquina de desenvolvimento:
# ninguém precisa montar volume para rodar `python main.py`.
DIRETORIO_DADOS = Path(os.environ.get("DIRETORIO_DADOS") or (RAIZ / "output"))
HISTORICO = DIRETORIO_DADOS / "historico.json"


def _historico() -> list[str]:
    if not HISTORICO.exists():
        return []
    try:
        dados = json.loads(HISTORICO.read_text(encoding="utf-8"))
        return [str(item) for item in dados] if isinstance(dados, list) else []
    except Exception:
        return []


def _registrar(chave: str, limite: int = 20) -> None:
    """Guarda as últimas combinações usadas. Falha aqui não derruba o fluxo."""
    try:
        usados = [*_historico(), chave][-limite:]
        HISTORICO.parent.mkdir(parents=True, exist_ok=True)
        HISTORICO.write_text(json.dumps(usados, ensure_ascii=False), encoding="utf-8")
    except Exception as erro:
        log.warning("Não foi possível gravar o histórico (%s).", erro)


def selecionar(
    config: dict[str, Any],
    sinal_id: str | None = None,
    sku: str | None = None,
    sinais_do_radar: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Escolhe o par (sinal, produto) desta execução.

    Com `sinal_id`/`sku` a escolha é determinística — útil para reproduzir uma
    execução. Sem eles, evita as combinações recentes.

    `sinais_do_radar` são assuntos lidos do mundo e já aprovados na triagem do
    módulo `radar`. Quando existem, têm preferência sobre o catálogo: são o que
    está em alta agora, e o catálogo é a curadoria que sempre funciona. Na
    maioria das leituras a lista vem vazia, porque quase tudo em alta é notícia.
    """
    sinais = config.get("sinais") or []
    if sinais_do_radar and not sinal_id:
        sinais = sinais_do_radar
    produtos = config.get("produtos") or []
    if not sinais or not produtos:
        raise ValueError("config.yaml precisa de ao menos um sinal e um produto.")

    if sinal_id:
        sinal = next((s for s in sinais if s.get("id") == sinal_id), None)
        if sinal is None:
            disponiveis = ", ".join(str(s.get("id")) for s in sinais)
            raise ValueError(f"Sinal '{sinal_id}' não existe. Disponíveis: {disponiveis}")
    else:
        sinal = None

    if sku:
        produto = next((p for p in produtos if p.get("sku") == sku), None)
        if produto is None:
            disponiveis = ", ".join(str(p.get("sku")) for p in produtos)
            raise ValueError(f"SKU '{sku}' não existe. Disponíveis: {disponiveis}")
    else:
        produto = None

    if sinal is None or produto is None:
        usados = set(_historico())
        combinacoes = [
            (s, p)
            for s in ([sinal] if sinal else sinais)
            for p in ([produto] if produto else produtos)
        ]
        inéditas = [
            par for par in combinacoes if f"{par[0]['id']}|{par[1]['sku']}" not in usados
        ]
        # Esgotadas todas as combinações, recomeça — melhor repetir depois de um
        # ciclo completo do que travar a automação.
        sinal, produto = random.choice(inéditas or combinacoes)

    chave = f"{sinal['id']}|{produto['sku']}"
    _registrar(chave)
    log.info("Sinal '%s' + produto '%s' selecionados.", sinal["id"], produto["sku"])

    return {
        "sinal": sinal,
        "produto": produto,
        "chave": chave,
        "data": date.today().isoformat(),
    }
