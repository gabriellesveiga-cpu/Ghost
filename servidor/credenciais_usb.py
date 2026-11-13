
import hashlib
import hmac
import json
import os
import threading
from datetime import datetime, timezone

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
    if not isinstance(segredo, str) or not 32 <= len(segredo) <= 256:
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

    try:
        hash_recebido = gerar_hash_usb(segredo)
    except UnicodeError:
        return False
    hash_salvo = registro.get("hash", "")
    if (not isinstance(hash_salvo, str) or len(hash_salvo) != 64
            or any(c not in "0123456789abcdef" for c in hash_salvo)):
        return False

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


def validar_substituicao(computador_id, novo_segredo):
    if not isinstance(novo_segredo, str) or not 32 <= len(novo_segredo) <= 256:
        raise ValueError("Nova credencial inválida.")
    with BLOQUEIO_USB:
        registro = carregar_credenciais().get(computador_id)
        if not isinstance(registro, dict) or registro.get("ativa") is not False:
            raise ValueError("A substituição exige uma credencial previamente revogada.")
        hash_anterior = registro.get("hash")
        if (not isinstance(hash_anterior, str) or len(hash_anterior) != 64
                or any(c not in "0123456789abcdef" for c in hash_anterior)):
            raise ValueError("Registro de credencial inválido.")
        if hmac.compare_digest(gerar_hash_usb(novo_segredo), hash_anterior):
            raise ValueError("A nova credencial deve ser diferente da anterior.")


def substituir_credencial(computador_id, novo_segredo):
    with BLOQUEIO_USB:
        validar_substituicao(computador_id, novo_segredo)
        credenciais = carregar_credenciais()
        credenciais[computador_id] = {
            "hash": gerar_hash_usb(novo_segredo), "ativa": True,
            "substituida_em": datetime.now(timezone.utc).isoformat(),
        }
        salvar_credenciais(credenciais)
