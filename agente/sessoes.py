
import requests

from solicitacoes import obter_autenticacao


URL_SERVIDOR = "http://127.0.0.1:8000"


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

    return resposta.json()["sessao"]


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
