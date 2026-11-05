
import json
from pathlib import Path

import requests

from identidade import carregar_identidade
from usb import listar_unidades_removiveis


URL_SERVIDOR = "http://127.0.0.1:8000"


def obter_credencial_usb(computador_id):
    for unidade in listar_unidades_removiveis():
        caminho = Path(unidade) / "keynexus.json"

        if not caminho.is_file():
            continue

        try:
            with caminho.open("r", encoding="utf-8") as arquivo:
                credencial = json.load(arquivo)

            if not isinstance(credencial, dict):
                continue

            if (
                credencial.get("aplicacao") == "KeyNexus"
                and credencial.get("versao") == 1
                and credencial.get("computador_id") == computador_id
                and isinstance(credencial.get("segredo_usb"), str)
                and len(credencial["segredo_usb"]) >= 32
            ):
                return credencial

        except (OSError, ValueError, TypeError):
            continue

    return None


def obter_autenticacao():
    identidade = carregar_identidade()

    if not identidade:
        raise RuntimeError(
            "Agente não possui identidade cadastrada."
        )

    computador_id = identidade["id"]

    credencial = obter_credencial_usb(computador_id)

    if credencial is None:
        raise RuntimeError(
            "Pendrive KeyNexus não encontrado."
        )

    return {
        "computador_id": computador_id,
        "chave_computador": identidade["chave"],
        "segredo_usb": credencial["segredo_usb"]
    }


def consultar_solicitacoes():
    autenticacao = obter_autenticacao()

    resposta = requests.post(
        f"{URL_SERVIDOR}/solicitacoes/consultar",
        json=autenticacao,
        timeout=5
    )

    resposta.raise_for_status()

    dados = resposta.json()

    return [
        solicitacao
        for solicitacao in dados.get("solicitacoes", [])
        if solicitacao.get("status") == "pendente"
    ]


def enviar_resposta(solicitacao_id, aceitar):
    autenticacao = obter_autenticacao()

    resposta = requests.post(
        f"{URL_SERVIDOR}/solicitacoes/responder",
        json={
            **autenticacao,
            "solicitacao_id": solicitacao_id,
            "aceitar": aceitar
        },
        timeout=5
    )

    resposta.raise_for_status()

    return resposta.json()
