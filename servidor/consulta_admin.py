
from fastapi import APIRouter, Depends, HTTPException

from .sessoes import buscar_sessao_ativa_computador


def criar_router_consulta_admin(exigir_admin, computadores):
    router = APIRouter(
        prefix="/admin/sessoes",
        tags=["Sessões administrativas"]
    )

    @router.get("/{computador_id}")
    def consultar_sessao_administrativa(
        computador_id: str,
        token: str = Depends(exigir_admin)
    ):
        computador = computadores.get(computador_id)

        if computador is None:
            raise HTTPException(
                status_code=404,
                detail="Computador não encontrado."
            )

        if computador.get("tipo") != "agente":
            raise HTTPException(
                status_code=400,
                detail="O computador selecionado não é um Agente."
            )

        sessao = buscar_sessao_ativa_computador(
            computador_id
        )

        if sessao is None:
            return {
                "computador_id": computador_id,
                "sessao_ativa": False,
                "visualizacao_autorizada": False,
                "sessao": None
            }

        permissoes = sessao.get("permissoes", [])

        visualizacao_autorizada = (
            "visualizacao" in permissoes
            and sessao.get("status") == "ativa"
        )

        return {
            "computador_id": computador_id,
            "sessao_ativa": True,
            "visualizacao_autorizada": visualizacao_autorizada,
            "sessao": {
                "id": sessao["id"],
                "status": sessao["status"],
                "permissoes": permissoes,
                "iniciada_em": sessao["iniciada_em"],
                "expira_em": sessao["expira_em"]
            }
        }

    return router
