
import requests
import threading

from solicitacoes import obter_autenticacao


URL_SERVIDOR = "http://127.0.0.1:8000"
_AUTORIZACOES = {}
_BLOQUEIO = threading.Lock()


def guardar_autorizacao_encerramento(sessao):
    if sessao and sessao.get("token_encerramento"):
        with _BLOQUEIO:
            _AUTORIZACOES[sessao["id"]] = {
                "sessao_id": sessao["id"],
                "computador_id": sessao["computador_id"],
                "token_encerramento": sessao["token_encerramento"],
            }


def iniciar_sessao(solicitacao_id, permissoes):
    autenticacao = obter_autenticacao()

    resposta = requests.post(
        f"{URL_SERVIDOR}/sessoes/iniciar",
        json={
            **autenticacao,
            "solicitacao_id": solicitacao_id,
            "permissoes": permissoes
        },
        timeout=5
    )

    resposta.raise_for_status()

    sessao = resposta.json()["sessao"]
    guardar_autorizacao_encerramento(sessao)
    return sessao


def consultar_sessao(sessao_id):
    autenticacao = obter_autenticacao()

    resposta = requests.post(
        f"{URL_SERVIDOR}/sessoes/consultar",
        json={
            **autenticacao,
            "sessao_id": sessao_id
        },
        timeout=5
    )

    resposta.raise_for_status()

    return resposta.json()["sessao"]


def recuperar_sessao(solicitacao_id, autenticacao_esperada=None):
    autenticacao = obter_autenticacao()
    if autenticacao_esperada is not None and autenticacao != autenticacao_esperada:
        raise RuntimeError("Identidade ou pendrive mudou durante a recuperação.")
    resposta = requests.post(
        f"{URL_SERVIDOR}/sessoes/recuperar",
        json={**autenticacao, "solicitacao_id": solicitacao_id}, timeout=5
    )
    resposta.raise_for_status()
    dados = resposta.json()
    guardar_autorizacao_encerramento(dados.get("sessao"))
    return dados


def registrar_atividade(sessao_id):
    autenticacao = obter_autenticacao()

    resposta = requests.post(
        f"{URL_SERVIDOR}/sessoes/atividade",
        json={
            **autenticacao,
            "sessao_id": sessao_id
        },
        timeout=5
    )

    resposta.raise_for_status()

    return resposta.json()["sessao"]


def encerrar_sessao(sessao_id):
    with _BLOQUEIO:
        autorizacao = _AUTORIZACOES.get(sessao_id)
    if autorizacao is not None:
        resposta = requests.post(
            f"{URL_SERVIDOR}/sessoes/encerrar-autorizado",
            json=autorizacao, timeout=5
        )
        resposta.raise_for_status()
        sessao = resposta.json()["sessao"]
        with _BLOQUEIO:
            _AUTORIZACOES.pop(sessao_id, None)
        return sessao

    # Compatibilidade com sessões antigas, anteriores à autorização restrita.
    autenticacao = obter_autenticacao()

    resposta = requests.post(
        f"{URL_SERVIDOR}/sessoes/encerrar",
        json={
            **autenticacao,
            "sessao_id": sessao_id
        },
        timeout=5
    )

    resposta.raise_for_status()

    return resposta.json()["sessao"]
