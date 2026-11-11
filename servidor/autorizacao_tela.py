
from .sessoes import consultar_sessao


def verificar_autorizacao_tela(sessao_id, computador_id):
    """
    Verifica se uma sessão possui autorização
    para visualização de tela.

    Esta função não inicia captura ou transmissão.
    """

    if not sessao_id or not computador_id:
        return {
            "autorizado": False,
            "motivo": "Identificação incompleta."
        }

    try:
        sessao = consultar_sessao(
            sessao_id,
            computador_id
        )

    except PermissionError:
        return {
            "autorizado": False,
            "motivo": "Sessão pertence a outro computador."
        }

    except (ValueError, OSError):
        return {
            "autorizado": False,
            "motivo": "Não foi possível validar a sessão."
        }

    if sessao is None:
        return {
            "autorizado": False,
            "motivo": "Sessão não encontrada."
        }

    if sessao.get("status") != "ativa":
        return {
            "autorizado": False,
            "motivo": "Sessão não está ativa."
        }

    permissoes = sessao.get("permissoes", [])

    if "visualizacao" not in permissoes:
        return {
            "autorizado": False,
            "motivo": "Visualização não autorizada."
        }

    return {
        "autorizado": True,
        "motivo": "Sessão autorizada para visualização.",
        "sessao_id": sessao["id"],
        "computador_id": computador_id
    }
