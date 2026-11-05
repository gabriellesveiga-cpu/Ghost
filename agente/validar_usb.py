
import requests

from identidade import carregar_identidade
from credencial_usb import (
    verificar_credencial_local,
    ler_credencial
)


URL_SERVIDOR = "http://127.0.0.1:8000"


def validar_usb_servidor():
    identidade = carregar_identidade()

    if identidade is None:
        return {
            "valida": False,
            "motivo": "Agente não vinculado."
        }

    resultado_local = verificar_credencial_local()

    if not resultado_local["valida"]:
        return {
            "valida": False,
            "motivo": resultado_local["motivo"]
        }

    unidade = resultado_local["unidade"]
    credencial = ler_credencial(unidade)

    if credencial is None:
        return {
            "valida": False,
            "motivo": "Não foi possível ler a credencial."
        }

    if credencial.get("computador_id") != identidade["id"]:
        return {
            "valida": False,
            "motivo": "Credencial de outro computador."
        }

    try:
        resposta = requests.post(
            f"{URL_SERVIDOR}/usb/validar",
            json={
                "computador_id": identidade["id"],
                "chave_computador": identidade["chave"],
                "segredo_usb": credencial["segredo_usb"]
            },
            timeout=5
        )

        if resposta.status_code == 401:
            return {
                "valida": False,
                "motivo": "Credencial rejeitada pelo servidor."
            }

        resposta.raise_for_status()

        dados = resposta.json()

        if dados.get("valida") is not True:
            return {
                "valida": False,
                "motivo": "Servidor não confirmou a credencial."
            }

        return {
            "valida": True,
            "motivo": "Credencial validada pelo servidor.",
            "unidade": unidade
        }

    except requests.RequestException:
        return {
            "valida": False,
            "motivo": "Não foi possível validar com o servidor."
        }


if __name__ == "__main__":
    print("=== KEYNEXUS — VALIDAÇÃO USB ===")

    resultado = validar_usb_servidor()

    if resultado["valida"]:
        print("\nCredencial USB validada pelo servidor!")
        print("Unidade:", resultado["unidade"])
    else:
        print("\nCredencial USB não validada.")
        print("Motivo:", resultado["motivo"])
