
import json
import secrets
from pathlib import Path

from identidade import carregar_identidade
from usb import listar_unidades_removiveis


NOME_ARQUIVO = "keynexus.json"
VERSAO = 1


def criar_credencial(unidade):
    identidade = carregar_identidade()

    if identidade is None:
        raise ValueError(
            "O agente precisa estar vinculado primeiro."
        )

    raiz = Path(unidade)

    if unidade not in listar_unidades_removiveis():
        raise ValueError(
            "A unidade selecionada não é removível."
        )

    caminho = raiz / NOME_ARQUIVO

    if caminho.exists():
        raise FileExistsError(
            "Já existe uma credencial nesta unidade."
        )

    credencial = {
        "aplicacao": "KeyNexus",
        "versao": VERSAO,
        "computador_id": identidade["id"],
        "segredo_usb": secrets.token_urlsafe(32)
    }

    # Criação exclusiva: não sobrescreve arquivos existentes.
    with caminho.open(
        "x",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            credencial,
            arquivo,
            indent=4,
            ensure_ascii=False
        )

    return caminho


def ler_credencial(unidade):
    caminho = Path(unidade) / NOME_ARQUIVO

    if not caminho.is_file():
        return None

    try:
        with caminho.open(
            "r",
            encoding="utf-8"
        ) as arquivo:
            dados = json.load(arquivo)

        if not isinstance(dados, dict):
            return None

        return dados

    except (OSError, ValueError, UnicodeError):
        return None


def verificar_credencial_local():
    identidade = carregar_identidade()

    if identidade is None:
        return {
            "valida": False,
            "motivo": "Agente não vinculado.",
            "unidade": None
        }

    for unidade in listar_unidades_removiveis():
        dados = ler_credencial(unidade)

        if dados is None:
            continue

        if dados.get("aplicacao") != "KeyNexus":
            continue

        if dados.get("versao") != VERSAO:
            continue

        if dados.get("computador_id") != identidade["id"]:
            continue

        segredo = dados.get("segredo_usb")

        if not isinstance(segredo, str) or len(segredo) < 32:
            continue

        return {
            "valida": True,
            "motivo": "Credencial local encontrada.",
            "unidade": unidade
        }

    return {
        "valida": False,
        "motivo": "Nenhuma credencial compatível encontrada.",
        "unidade": None
    }
