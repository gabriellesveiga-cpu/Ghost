
import hashlib
import hmac
import json
import os
import secrets
import threading

from pathlib import Path


PASTA_DADOS = Path(__file__).resolve().parent / "dados"
ARQUIVO = PASTA_DADOS / "credenciais_usb.json"

BLOQUEIO_USB = threading.RLock()


def gerar_hash_usb(segredo):
    return hashlib.sha256(
        segredo.encode("utf-8")
    ).hexdigest()


def carregar_credenciais():
    PASTA_DADOS.mkdir(
        parents=True,
        exist_ok=True
    )

    if not ARQUIVO.exists():
        return {}

    with ARQUIVO.open(
        "r",
        encoding="utf-8"
    ) as arquivo:
        dados = json.load(arquivo)

    if not isinstance(dados, dict):
        raise ValueError(
            "Arquivo de credenciais inválido."
        )

    return dados


def salvar_credenciais(dados):
    PASTA_DADOS.mkdir(
        parents=True,
        exist_ok=True
    )

    temporario = ARQUIVO.with_suffix(".tmp")

    with temporario.open(
        "w",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            dados,
            arquivo,
            indent=4,
            ensure_ascii=False
        )

    os.replace(temporario, ARQUIVO)


def registrar_credencial(computador_id, segredo):
    if not isinstance(segredo, str) or len(segredo) < 32:
        raise ValueError(
            "Segredo USB inválido."
        )

    with BLOQUEIO_USB:
        credenciais = carregar_credenciais()

        if computador_id in credenciais:
            raise ValueError(
                "Este computador já possui uma credencial USB."
            )

        credenciais[computador_id] = {
            "hash": gerar_hash_usb(segredo),
            "ativa": True
        }

        salvar_credenciais(credenciais)

    return True


def validar_credencial(computador_id, segredo):
    if not isinstance(segredo, str):
        return False

    with BLOQUEIO_USB:
        credenciais = carregar_credenciais()
        registro = credenciais.get(computador_id)

    if not isinstance(registro, dict):
        return False

    if not registro.get("ativa", False):
        return False

    hash_recebido = gerar_hash_usb(segredo)
    hash_salvo = registro.get("hash", "")

    return hmac.compare_digest(
        hash_recebido,
        hash_salvo
    )


def revogar_credencial(computador_id):
    with BLOQUEIO_USB:
        credenciais = carregar_credenciais()

        if computador_id not in credenciais:
            return False

        credenciais[computador_id]["ativa"] = False

        salvar_credenciais(credenciais)

    return True
