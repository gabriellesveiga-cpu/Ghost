
import json
import os
from pathlib import Path

import requests


URL_SERVIDOR = "http://127.0.0.1:8000"

PASTA_IDENTIDADE = (
    Path.home() / "AppData" / "Local" / "KeyNexus"
)

ARQUIVO_IDENTIDADE = PASTA_IDENTIDADE / "identidade.json"


def identidade_existe():
    return ARQUIVO_IDENTIDADE.is_file()


def salvar_identidade(identificador, chave):
    PASTA_IDENTIDADE.mkdir(
        parents=True,
        exist_ok=True
    )

    dados = {
        "id": identificador,
        "chave": chave
    }

    temporario = ARQUIVO_IDENTIDADE.with_suffix(".tmp")

    try:
        with open(
            temporario,
            "w",
            encoding="utf-8"
        ) as arquivo:
            json.dump(dados, arquivo, indent=4)

        os.replace(temporario, ARQUIVO_IDENTIDADE)

    finally:
        if temporario.exists():
            temporario.unlink()


def carregar_identidade():
    if not identidade_existe():
        return None

    with open(
        ARQUIVO_IDENTIDADE,
        "r",
        encoding="utf-8"
    ) as arquivo:
        dados = json.load(arquivo)

    if not isinstance(dados, dict):
        raise ValueError("Identidade inválida.")

    if not isinstance(dados.get("id"), str):
        raise ValueError("ID inválido.")

    if not isinstance(dados.get("chave"), str):
        raise ValueError("Chave inválida.")

    return dados


def autenticar_agente():
    identidade = carregar_identidade()

    if identidade is None:
        return {
            "autenticado": False,
            "motivo": "Agente não vinculado."
        }

    try:
        resposta = requests.post(
            f"{URL_SERVIDOR}/autenticar",
            json=identidade,
            timeout=5
        )

        if resposta.status_code == 401:
            return {
                "autenticado": False,
                "motivo": "Credencial rejeitada."
            }

        resposta.raise_for_status()

        dados = resposta.json()

        computador = dados.get("computador", {})

        if computador.get("tipo") != "agente":
            return {
                "autenticado": False,
                "motivo": "Identidade não pertence a um agente."
            }

        return {
            "autenticado": True,
            "computador": computador
        }

    except requests.RequestException:
        return {
            "autenticado": False,
            "motivo": "Servidor indisponível."
        }
