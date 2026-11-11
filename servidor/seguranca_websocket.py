
from fastapi import HTTPException

from .autorizacao_tela import verificar_autorizacao_tela


def validar_sessao_websocket(
    sessao_id,
    computador_id
):
    """
    Verifica a autorização de visualização.

    Esta função não autentica o participante
    nem autoriza uma conexão por conta própria.
    """

    resultado = verificar_autorizacao_tela(
        sessao_id,
        computador_id
    )

    if not resultado.get("autorizado"):
        return {
            "permitido": False,
            "motivo": resultado.get(
                "motivo",
                "Acesso não autorizado."
            )
        }

    return {
        "permitido": True,
        "motivo": "Sessão autorizada.",
        "sessao_id": sessao_id,
        "computador_id": computador_id
    }


def validar_administrador_websocket(
    token,
    sessoes_admin,
    bloqueio,
    relogio
):
    """
    Confere um token administrativo existente.

    O dicionário de sessões, o bloqueio e o
    relógio são fornecidos pelo servidor.
    """

    if not isinstance(token, str) or not token:
        return False

    with bloqueio:
        expiracao = sessoes_admin.get(token)

        if expiracao is None:
            return False

        if relogio() >= expiracao:
            sessoes_admin.pop(token, None)
            return False

    return True


def validar_agente_websocket(
    computador_id,
    chave_computador,
    segredo_usb,
    verificar_agente
):
    """
    Reutiliza a validação de identidade e USB
    existente no servidor.
    """

    try:
        verificar_agente(
            computador_id,
            chave_computador,
            segredo_usb
        )

    except HTTPException:
        return False

    return True
