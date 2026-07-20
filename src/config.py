"""Carrega config.yaml com fallback embutido.

Configuração ausente ou inválida não derruba a execução: o sistema avisa e
segue com os padrões. Mesmo contrato do Desafio 1.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent

PADRAO: dict[str, Any] = {
    "marca": {
        "nome": "GoCase",
        "voz": "Direta, jovem e brasileira.",
        "logo": "marca/gocase.png",
        "paleta": {
            "primaria": "#FF5A1F",
            "secundaria": "#1A1A2E",
            "destaque": "#FFD166",
            "fundo": "#F7F7F9",
        },
        "proibido": [],
    },
    "produtos": [
        {
            "sku": "CASE-IPH-15P",
            "nome": "Capinha iPhone 15 Pro",
            "linha": "Impact Pro",
            "area_arte": [1024, 1024],
        }
    ],
    "sinais": [
        {"id": "generico", "tema": "personalização sob demanda", "publico": "18-30"}
    ],
    "video": {
        "largura": 1080,
        "altura": 1920,
        "fps": 30,
        "duracao_segundos": 8,
        "codec": "libx264",
        "fallback_zoom": 1.18,
    },
    "publicacao": {
        "privacidade_desejada": "PUBLIC_TO_EVERYONE",
        "permitir_comentario": True,
        "permitir_duet": True,
        "permitir_stitch": True,
        "feito_com_ia": True,
        "tipo_conteudo_comercial": "brand_organic",
        "tentativas_status": 20,
        "intervalo_status_segundos": 6,
    },
    "ia": {
        "usar_ia_imagem": True,
        "usar_ia_video": False,
        "modelo_texto": "claude-opus-4-8",
        "modelo_imagem": "gemini-3.1-flash-image",
        "modelo_video": "veo-3.1-fast-generate-preview",
        "max_tokens": 1200,
    },
}


def _fundir(padrao: dict, vindo: dict) -> dict:
    """Funde recursivamente, preservando as chaves do padrão que faltarem."""
    saida = dict(padrao)
    for chave, valor in (vindo or {}).items():
        if isinstance(valor, dict) and isinstance(saida.get(chave), dict):
            saida[chave] = _fundir(saida[chave], valor)
        else:
            saida[chave] = valor
    return saida


def carregar(caminho: str | Path | None = None) -> dict[str, Any]:
    arquivo = Path(caminho) if caminho else RAIZ / "config.yaml"
    if not arquivo.exists():
        log.warning("config.yaml não encontrado em %s; usando padrões.", arquivo)
        return dict(PADRAO)
    try:
        lido = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}
        if not isinstance(lido, dict):
            raise ValueError("raiz do YAML não é um mapa")
        return _fundir(PADRAO, lido)
    except Exception as erro:  # YAML inválido não pode derrubar o serviço
        log.warning("config.yaml inválido (%s); usando padrões.", erro)
        return dict(PADRAO)


def segredo(nome: str, obrigatorio: bool = False) -> str | None:
    """Lê credencial do ambiente. Nunca vem de arquivo versionado."""
    valor = os.environ.get(nome) or None
    if obrigatorio and not valor:
        raise RuntimeError(
            f"Variável de ambiente {nome} não definida. Veja .env.example."
        )
    return valor


def modo_rascunho() -> bool:
    """Publicar é o padrão.

    O Creator Inbox parecia mais seguro, mas a TikTok aceita no máximo 5
    rascunhos pendentes por conta em 24h e não oferece API para limpá-los —
    uma rodada de testes trava a conta e a saída é manual, um a um no
    aplicativo. Modo de teste que exige limpeza manual não é modo de teste.
    """
    return os.environ.get("MODO_RASCUNHO", "false").strip().lower() == "true"
