"""Publicação no TikTok via Zernio.

Zernio é um cliente auditado da Content Posting API oficial da TikTok. Ele
resolve o único bloqueio que impede um fluxo n8n de publicar publicamente:
a auditoria da TikTok, que exige uma interface de usuário inspecionável e por
isso é inalcançável para uma automação headless. O README registra a decisão.

Quatro comportamentos documentados da API são tratados aqui de forma explícita,
porque cada um já causou falha em produção de outros integradores:

1. `x-request-id` — a doc do Zernio alerta que ferramentas de workflow tendem a
   reusar um único ID por execução. Toda chamada após a primeira seria tratada
   como retry e devolveria o post original. Geramos um UUID por chamada.
2. Dedup por hash de conteúdo — conteúdo idêntico na mesma conta dentro de 24h
   retorna HTTP 409. Traduzimos para uma mensagem acionável.
3. Níveis de privacidade variam por criador — consultamos `creator-info` antes
   de publicar e rebaixamos para uma opção permitida em vez de falhar.
4. Taxa de falha de ~13% na plataforma — publicação é assíncrona e o status
   real só aparece no polling. Não existe fire-and-forget aqui.
"""

from __future__ import annotations

import logging
import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

BASE = "https://zernio.com/api/v1"
LIMITE_UPLOAD_BYTES = 25 * 1024 * 1024  # /media/upload-direct recusa acima disso


class ErroPublicacao(RuntimeError):
    """Falha tratada da publicação, com mensagem legível para o operador."""


class Publicador:
    def __init__(self, api_key: str, timeout: float = 120.0) -> None:
        if not api_key:
            raise ErroPublicacao("ZERNIO_API_KEY ausente.")
        self._cliente = httpx.Client(
            base_url=BASE,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def __enter__(self) -> "Publicador":
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    def fechar(self) -> None:
        self._cliente.close()

    # ------------------------------------------------------------------ contas

    def listar_contas(self) -> list[dict[str, Any]]:
        resposta = self._cliente.get("/accounts")
        self._conferir(resposta, "listar contas")
        corpo = resposta.json()
        contas = corpo.get("accounts", corpo) if isinstance(corpo, dict) else corpo
        return contas if isinstance(contas, list) else []

    def conta_tiktok(self, account_id: str | None = None) -> str:
        """Resolve o accountId do TikTok, por parâmetro ou por descoberta.

        Contas com token morto (`needsReconnection`) ou desativadas são
        ignoradas na descoberta — publicar nelas falharia mais adiante, com
        uma mensagem bem menos clara.
        """
        if account_id:
            return account_id

        tiktoks = [
            c for c in self.listar_contas()
            if str(c.get("platform", "")).lower() == "tiktok"
        ]
        saudaveis = [
            c for c in tiktoks
            if c.get("isActive", True) and not c.get("needsReconnection", False)
        ]

        for conta in saudaveis:
            encontrado = conta.get("_id") or conta.get("id")
            if encontrado:
                log.info(
                    "Conta TikTok descoberta: %s (@%s)",
                    encontrado,
                    conta.get("username", "?"),
                )
                return str(encontrado)

        if tiktoks:
            raise ErroPublicacao(
                f"{len(tiktoks)} conta(s) TikTok encontrada(s), nenhuma utilizável "
                "— token expirado ou conta desativada. Reconecte pelo painel do Zernio."
            )
        raise ErroPublicacao(
            "Nenhuma conta TikTok conectada no Zernio. Conecte pelo painel e "
            "informe ZERNIO_TIKTOK_ACCOUNT_ID."
        )

    def info_criador(self, account_id: str) -> dict[str, Any]:
        """Consulta o que a conta do criador aceita agora.

        Devolve `{privacidades, pode_postar, duracao_maxima}`. A doc da TikTok
        é explícita: usar um nível de privacidade fora da lista faz o post
        falhar. Falha nesta consulta não é fatal — devolvemos vazio e o
        chamador segue sem a checagem.
        """
        vazio: dict[str, Any] = {
            "privacidades": [],
            "pode_postar": None,
            "duracao_maxima": None,
        }
        try:
            resposta = self._cliente.get(
                f"/accounts/{account_id}/tiktok/creator-info",
                params={"mediaType": "video"},
            )
            if resposta.status_code == 429:
                raise ErroPublicacao(
                    "A conta atingiu o limite diário de publicações por API da "
                    "TikTok. Aguarde a janela de 24h ou publique pelo aplicativo."
                )
            self._conferir(resposta, "consultar creator-info")
            corpo = resposta.json()
        except ErroPublicacao:
            raise
        except Exception as erro:
            log.warning("creator-info indisponível (%s); seguindo sem checagem.", erro)
            return vazio

        return {
            "privacidades": self._extrair_privacidades(corpo),
            "pode_postar": (corpo.get("creator") or {}).get("canPostMore"),
            "duracao_maxima": (corpo.get("postingLimits") or {}).get(
                "maxVideoDurationSec"
            ),
        }

    @staticmethod
    def _extrair_privacidades(corpo: dict[str, Any]) -> list[str]:
        """`privacyLevels` é uma lista de objetos `{value, label}`, não de strings.

        Tratar cada item como string produziria `"{'value': 'PUBLIC_TO_EVERYONE',
        ...}"`, a comparação nunca casaria e todo post seria rebaixado para um
        nível inválido. Aceitamos as duas formas por segurança.
        """
        bruto = corpo.get("privacyLevels") or corpo.get("privacy_level_options") or []
        if not isinstance(bruto, list):
            return []
        niveis: list[str] = []
        for item in bruto:
            if isinstance(item, dict):
                valor = item.get("value") or item.get("privacy_level")
                if valor:
                    niveis.append(str(valor))
            elif isinstance(item, str):
                niveis.append(item)
        return niveis

    # ------------------------------------------------------------------- mídia

    def subir_midia(self, caminho: str | Path) -> str:
        """Envia o arquivo e devolve a URL pública que a TikTok vai baixar.

        Usar o storage do Zernio evita hospedar mídia por conta própria. A doc
        rejeita explicitamente Drive, Dropbox e OneDrive — eles devolvem HTML,
        não bytes de vídeo.
        """
        arquivo = Path(caminho)
        if not arquivo.exists():
            raise ErroPublicacao(f"Arquivo de mídia não encontrado: {arquivo}")

        tamanho = arquivo.stat().st_size
        if tamanho > LIMITE_UPLOAD_BYTES:
            raise ErroPublicacao(
                f"Mídia com {tamanho / 1024 / 1024:.1f} MB excede o limite de 25 MB "
                "do upload direto. Reduza a duração ou o bitrate do vídeo."
            )

        tipo = mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
        with arquivo.open("rb") as binario:
            resposta = self._cliente.post(
                "/media/upload-direct",
                files={"file": (arquivo.name, binario, tipo)},
            )
        self._conferir(resposta, "subir mídia")
        url = resposta.json().get("url")
        if not url:
            raise ErroPublicacao("Upload aceito, mas a resposta não trouxe 'url'.")
        log.info("Mídia publicada em %s (%.1f MB)", url, tamanho / 1024 / 1024)
        return str(url)

    # -------------------------------------------------------------- publicação

    def publicar(
        self,
        *,
        account_id: str,
        legenda: str,
        url_video: str,
        privacidade: str = "PUBLIC_TO_EVERYONE",
        permitir_comentario: bool = True,
        permitir_duet: bool = True,
        permitir_stitch: bool = True,
        feito_com_ia: bool = True,
        tipo_conteudo_comercial: str = "brand_organic",
        rascunho: bool = False,
    ) -> dict[str, Any]:
        """Cria o post.

        `rascunho=True` envia para o **Creator Inbox da TikTok** — a mídia
        percorre todo o caminho até a plataforma e o criador finaliza pelo
        aplicativo. Não confundir com `isDraft` do Zernio, que guarda o post no
        painel e nunca chega à TikTok; esse modo não exercitaria nada do que
        importa testar. Internamente o Creator Inbox usa `post_mode:
        MEDIA_UPLOAD`, contra o `DIRECT_POST` da publicação normal.
        """
        info = self.info_criador(account_id)
        permitidas = info["privacidades"]

        if info["pode_postar"] is False:
            raise ErroPublicacao(
                "A TikTok informa que esta conta não pode publicar mais agora "
                "(limite diário por API). Aguarde a janela de 24h."
            )

        if permitidas and privacidade not in permitidas:
            escolhida = permitidas[0]
            log.warning(
                "Privacidade %s indisponível para este criador; usando %s. "
                "Permitidas: %s",
                privacidade,
                escolhida,
                ", ".join(permitidas),
            )
            privacidade = escolhida

        # A TikTok recusa conteúdo de parceria paga com visibilidade privada.
        if tipo_conteudo_comercial == "brand_content" and privacidade == "SELF_ONLY":
            raise ErroPublicacao(
                "A TikTok não aceita 'brand_content' com privacidade SELF_ONLY. "
                "Use 'brand_organic' ou uma privacidade pública."
            )

        ajustes: dict[str, Any] = {
            "privacy_level": privacidade,
            "allow_comment": permitir_comentario,
            "allow_duet": permitir_duet,
            "allow_stitch": permitir_stitch,
            # Exigência legal da TikTok. Ambos precisam ser true.
            "content_preview_confirmed": True,
            "express_consent_given": True,
            # Divulgação de conteúdo gerado por IA — política da plataforma.
            "video_made_with_ai": feito_com_ia,
            # Sozinho já basta: 'brand_organic' implica isBrandOrganicPost, então
            # não enviamos os booleanos separados.
            "commercialContentType": tipo_conteudo_comercial,
        }
        if rascunho:
            ajustes["draft"] = True

        corpo = {
            "content": legenda,
            "mediaItems": [{"type": "video", "url": url_video}],
            "platforms": [{"platform": "tiktok", "accountId": account_id}],
            "tiktokSettings": ajustes,
            # Sempre true: o post precisa sair do Zernio rumo à TikTok. O que
            # decide se vai ao ar ou para o inbox é tiktokSettings.draft.
            "publishNow": True,
        }

        resposta = self._cliente.post(
            "/posts",
            json=corpo,
            # UUID novo a cada chamada. Reusar ID entre nós de workflow faz a
            # segunda chamada devolver o post da primeira, silenciosamente.
            headers={"x-request-id": str(uuid.uuid4())},
        )

        if resposta.status_code == 409:
            detalhes = self._json_seguro(resposta).get("details", {})
            raise ErroPublicacao(
                "Zernio recusou por conteúdo duplicado nas últimas 24h "
                f"(post original: {detalhes.get('existingPostId', 'desconhecido')}). "
                "Varie a legenda ou a mídia para publicar de novo."
            )

        self._conferir(resposta, "criar post")
        post = self._json_seguro(resposta).get("post", {})
        post_id = post.get("_id") or post.get("id")
        log.info("Post criado: %s (rascunho=%s)", post_id, rascunho)
        return {
            "post_id": post_id,
            "status": post.get("status"),
            "url_publica": self._extrair_url(post),
            "rascunho": rascunho,
        }

    def aguardar_publicacao(
        self, post_id: str, tentativas: int = 20, intervalo: float = 6.0
    ) -> dict[str, Any]:
        """Acompanha o post até o estado final.

        A publicação é assíncrona: o 201 do POST só diz que o pedido foi aceito.
        Com ~13% de falha na plataforma, o resultado real só existe aqui.
        """
        ultimo: dict[str, Any] = {}
        for tentativa in range(1, tentativas + 1):
            resposta = self._cliente.get(f"/posts/{post_id}")
            self._conferir(resposta, "consultar status do post")
            corpo = self._json_seguro(resposta)
            ultimo = corpo.get("post", corpo)
            estado = str(ultimo.get("status", "")).lower()
            log.info("Status do post %s: %s (tentativa %d)", post_id, estado, tentativa)

            # A doc lista seis estados: draft, scheduled, publishing, published,
            # failed e partial. Só 'publishing' é transitório — tratar qualquer
            # outro como "espere mais" faria o polling girar até estourar.
            if estado in {"published", "partial"}:
                return {
                    "estado": estado,
                    "url_publica": self._extrair_url(ultimo),
                    "detalhe": ultimo,
                }
            if estado == "failed":
                raise ErroPublicacao(
                    f"TikTok recusou a publicação: {self._motivo_falha(ultimo)}"
                )
            if estado in {"draft", "scheduled"}:
                raise ErroPublicacao(
                    f"O post ficou em '{estado}' em vez de ser enviado. Isso "
                    "indica que publishNow não foi aceito — confira o payload."
                )
            time.sleep(intervalo)

        raise ErroPublicacao(
            f"Status ainda '{ultimo.get('status', 'desconhecido')}' após "
            f"{tentativas} consultas. O post pode concluir depois — confira o "
            "painel do Zernio antes de reenviar, para não duplicar."
        )

    # ---------------------------------------------------------------- internos

    @staticmethod
    def _json_seguro(resposta: httpx.Response) -> dict[str, Any]:
        try:
            corpo = resposta.json()
            return corpo if isinstance(corpo, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _extrair_url(post: dict[str, Any]) -> str | None:
        direto = post.get("platformPostUrl")
        if isinstance(direto, str):
            return direto
        if isinstance(direto, dict) and direto:
            return str(next(iter(direto.values())))
        for plataforma in post.get("platforms", []) or []:
            if isinstance(plataforma, dict) and plataforma.get("platformPostUrl"):
                return str(plataforma["platformPostUrl"])
        return None

    @staticmethod
    def _motivo_falha(post: dict[str, Any]) -> str:
        for chave in ("error", "errorMessage", "failureReason", "message"):
            if post.get(chave):
                return str(post[chave])
        for plataforma in post.get("platforms", []) or []:
            if isinstance(plataforma, dict):
                for chave in ("error", "errorMessage"):
                    if plataforma.get(chave):
                        return str(plataforma[chave])
        return "motivo não informado pela API"

    def _conferir(self, resposta: httpx.Response, acao: str) -> None:
        if resposta.is_success:
            return
        corpo = self._json_seguro(resposta)
        detalhe = corpo.get("error") or resposta.text[:300]
        if resposta.status_code == 401:
            raise ErroPublicacao(
                f"Zernio recusou a credencial ao {acao}. Confira ZERNIO_API_KEY."
            )
        if resposta.status_code == 403 and corpo.get("code") == "ACCOUNT_DISCONNECTED":
            raise ErroPublicacao(
                "A conta TikTok foi desconectada do Zernio. Reconecte e atualize "
                "ZERNIO_TIKTOK_ACCOUNT_ID."
            )
        raise ErroPublicacao(f"Falha ao {acao} (HTTP {resposta.status_code}): {detalhe}")
