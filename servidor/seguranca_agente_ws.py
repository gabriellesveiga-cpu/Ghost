from fastapi import HTTPException

from .autorizacao_tela import verificar_autorizacao_tela


def verificar_agente_para_websocket(
    computador_id,
    chave_computador,
    segredo_usb,
    sessao_id,
    verificar_identidade_usb
):
    """
    Valida a identidade do Agente,
    a credencial USB registrada e
    a permissao da sessao.

    Esta verificacao nao comprova que
    o pendrive continua fisicamente conectado.
    """

    if not all([
        computador_id,
        chave_computador,
        segredo_usb,
        sessao_id
    ]):
        return {
            "autorizado": False,
            "motivo": "Credenciais incompletas."
        }

    try:
        verificar_identidade_usb(
            computador_id,
            chave_computador,
            segredo_usb
        )

    except HTTPException:
        return {
            "autorizado": False,
            "motivo": "Identidade ou USB invalida."
        }

    resultado = verificar_autorizacao_tela(
        sessao_id,
        computador_id
    )

    if not resultado.get("autorizado"):
        return {
            "autorizado": False,
            "motivo": resultado.get(
                "motivo",
                "Sessao nao autorizada."
            )
        }

    return {
        "autorizado": True,
        "motivo": "Agente e sessao validados.",
        "computador_id": computador_id,
        "sessao_id": sessao_id
    }
