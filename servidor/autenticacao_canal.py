
from .autorizacao_tela import verificar_autorizacao_tela


def verificar_acesso_canal(
    sessao_id,
    computador_id,
    papel
):
    """
    Verifica a sessão e a permissão de visualização.

    Não autentica a identidade do participante.
    Não valida a credencial USB.
    """

    if papel not in ("agente", "administrador"):
        return {
            "autorizado": False,
            "motivo": "Papel desconhecido."
        }

    resultado = verificar_autorizacao_tela(
        sessao_id,
        computador_id
    )

    if not resultado["autorizado"]:
        return resultado

    return {
        "autorizado": True,
        "motivo": "Sessão permite visualização.",
        "papel": papel,
        "sessao_id": sessao_id,
        "computador_id": computador_id
    }
