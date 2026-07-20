"""Execução por terminal — para desenvolvimento e para a evidência do teste.

    python main.py                      # rascunho, sinal e produto automáticos
    python main.py --publicar           # publica de verdade
    python main.py --sinal gamer-neon --sku CASE-SAM-S24
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from dotenv import load_dotenv

from src.agente import executar_pipeline


def main() -> int:
    load_dotenv()
    analisador = argparse.ArgumentParser(
        description="Radar de Tendência — da tendência à capinha publicada."
    )
    analisador.add_argument("--sinal", help="ID do sinal de tendência (ver config.yaml)")
    analisador.add_argument("--sku", help="SKU do produto (ver config.yaml)")
    analisador.add_argument(
        "--publicar",
        action="store_true",
        help=(
            "Publica direto no perfil. Sem esta flag, envia para o Creator "
            "Inbox da TikTok — atravessa a integração inteira sem ficar público."
        ),
    )
    analisador.add_argument("--json", action="store_true", help="Imprime o relatório em JSON")
    args = analisador.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        relatorio = executar_pipeline(
            sinal_id=args.sinal,
            sku=args.sku,
            rascunho=not args.publicar,
        )
    except Exception as erro:
        print(f"\nFalhou: {erro}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    else:
        print()
        print(f"  Produto ........ {relatorio['produto']['nome']}")
        print(f"  Tendência ...... {relatorio['sinal']['tema']}")
        print(f"  Gancho ......... {relatorio['criativo']['gancho']}")
        print(f"  Arte ........... {relatorio['etapas']['arte']}")
        print(f"  Vídeo .......... {relatorio['etapas']['video']} · {relatorio['video_mb']} MB")
        print(f"  Estado ......... {relatorio['estado']}")
        if relatorio.get("url_publica"):
            print(f"  No ar .......... {relatorio['url_publica']}")
        elif relatorio.get("url_perfil"):
            print(f"  Perfil ......... {relatorio['url_perfil']}")
            print("                   (a TikTok não devolveu o link direto do post)")
        if relatorio.get("aviso"):
            print(f"  Aviso .......... {relatorio['aviso']}")
        print(f"  Tempo .......... {relatorio['segundos']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
