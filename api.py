"""Superfície HTTP — jobs assíncronos.

Por que assíncrono e não um endpoint que devolve o resultado direto: a geração
de vídeo por IA leva de 1 a 3 minutos. Nenhum request HTTP síncrono sobrevive a
isso — nem no n8n, nem em plano gratuito de hospedagem, nem em proxy nenhum.

O n8n dispara `POST /publicar`, recebe um `job_id` e consulta
`GET /jobs/{id}` até o estado final. O polling tem um efeito colateral útil:
mantém tráfego constante, o que impede o serviço de hibernar no meio do job.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.agente import executar_pipeline

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(
    title="Radar de Tendência — GoCase",
    description=(
        "Da tendência à capinha publicada no TikTok. Business case para o "
        "processo seletivo de Estágio em RPA na GoCase (GoGroup)."
    ),
    version="1.0.0",
)

# Jobs em memória. Escopo consciente: o serviço roda uma instância e os jobs
# são efêmeros por natureza. Persistência entra junto com múltiplas réplicas.
_JOBS: dict[str, dict[str, Any]] = {}
_TRAVA = threading.Lock()
_VALIDADE_SEGUNDOS = 3600


class PedidoPublicacao(BaseModel):
    sinal_id: str | None = Field(
        default=None,
        description="Fixa o sinal de tendência. Ausente, o sistema escolhe um inédito.",
    )
    sku: str | None = Field(
        default=None, description="Fixa o produto. Ausente, o sistema escolhe."
    )
    rascunho: bool | None = Field(
        default=None,
        description=(
            "true gera tudo sem publicar. Ausente, usa a variável de ambiente "
            "MODO_RASCUNHO (padrão: true)."
        ),
    )


def _limpar_expirados() -> None:
    agora = time.time()
    for job_id in [
        j for j, d in _JOBS.items() if agora - d.get("criado_em", agora) > _VALIDADE_SEGUNDOS
    ]:
        _JOBS.pop(job_id, None)


def _executar(job_id: str, pedido: PedidoPublicacao) -> None:
    def progresso(etapa: str, mensagem: str) -> None:
        with _TRAVA:
            if job_id in _JOBS:
                _JOBS[job_id]["etapa"] = etapa
                _JOBS[job_id]["mensagem"] = mensagem

    try:
        relatorio = executar_pipeline(
            sinal_id=pedido.sinal_id,
            sku=pedido.sku,
            rascunho=pedido.rascunho,
            progresso=progresso,
        )
        with _TRAVA:
            _JOBS[job_id].update(
                {"estado": "concluido", "etapa": "fim", "relatorio": relatorio}
            )
    except Exception as erro:  # o job carrega o erro; o serviço segue de pé
        log.exception("Job %s falhou", job_id)
        with _TRAVA:
            _JOBS[job_id].update(
                {"estado": "falhou", "erro": str(erro), "tipo_erro": type(erro).__name__}
            )


@app.get("/", summary="Saúde do serviço")
def saude() -> dict[str, Any]:
    with _TRAVA:
        _limpar_expirados()
        ativos = sum(1 for d in _JOBS.values() if d["estado"] == "executando")
    return {"servico": "radar-tendencia-gocase", "status": "ok", "jobs_ativos": ativos}


@app.post("/publicar", status_code=202, summary="Dispara uma publicação")
def publicar(pedido: PedidoPublicacao) -> dict[str, str]:
    """Aceita o pedido e devolve o `job_id`. Não bloqueia."""
    with _TRAVA:
        _limpar_expirados()
        job_id = str(uuid.uuid4())
        _JOBS[job_id] = {
            "estado": "executando",
            "etapa": "inicio",
            "mensagem": "Job aceito",
            "criado_em": time.time(),
        }

    threading.Thread(target=_executar, args=(job_id, pedido), daemon=True).start()
    return {"job_id": job_id, "consultar": f"/jobs/{job_id}"}


@app.get("/jobs/{job_id}", summary="Estado de um job")
def consultar(job_id: str) -> dict[str, Any]:
    with _TRAVA:
        job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job não encontrado. Jobs expiram 1 hora após a criação.",
        )
    return {"job_id": job_id, **{k: v for k, v in job.items() if k != "criado_em"}}


@app.get("/jobs/{job_id}/video", summary="Baixa o vídeo gerado")
def baixar_video(job_id: str) -> FileResponse:
    with _TRAVA:
        job = _JOBS.get(job_id)
    if job is None or job.get("estado") != "concluido":
        raise HTTPException(status_code=404, detail="Job inexistente ou ainda em execução.")
    caminho = job["relatorio"]["arquivos"]["video"]
    return FileResponse(caminho, media_type="video/mp4", filename="post.mp4")


@app.get("/catalogo", summary="Sinais e produtos disponíveis")
def catalogo() -> dict[str, Any]:
    """Permite ao n8n montar a lista de opções sem duplicar o config.yaml."""
    from src.config import carregar

    cfg = carregar()
    return {
        "sinais": [
            {"id": s["id"], "tema": s["tema"], "publico": s.get("publico")}
            for s in cfg["sinais"]
        ],
        "produtos": [
            {"sku": p["sku"], "nome": p["nome"], "linha": p.get("linha")}
            for p in cfg["produtos"]
        ],
    }
