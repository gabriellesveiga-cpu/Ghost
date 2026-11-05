
import getpass
import json
from pathlib import Path

import requests


URL_SERVIDOR = "http://127.0.0.1:8000"


def localizar_credencial():
    print("\n=== LOCALIZAR PENDRIVE KEYNEXUS ===")

    letra = input(
        "Letra do pendrive (exemplo: D): "
    ).strip().upper().replace(":", "").replace("\\", "")

    if len(letra) != 1 or not letra.isalpha():
        raise ValueError("Letra da unidade inválida.")

    caminho = Path(f"{letra}:\\") / "keynexus.json"

    if not caminho.is_file():
        raise FileNotFoundError(
            f"Credencial não encontrada em {caminho}"
        )

    with caminho.open("r", encoding="utf-8") as arquivo:
        credencial = json.load(arquivo)

    if not isinstance(credencial, dict):
        raise ValueError("Formato de credencial inválido.")

    if credencial.get("aplicacao") != "KeyNexus":
        raise ValueError("Arquivo não pertence ao KeyNexus.")

    if credencial.get("versao") != 1:
        raise ValueError("Versão da credencial incompatível.")

    computador_id = credencial.get("computador_id")
    segredo = credencial.get("segredo_usb")

    if not isinstance(computador_id, str) or not computador_id:
        raise ValueError("ID do computador inválido.")

    if not isinstance(segredo, str) or len(segredo) < 32:
        raise ValueError("Segredo USB inválido.")

    return computador_id, segredo, caminho


def main():
    print("=== KEYNEXUS — REGISTRO DE CREDENCIAL USB ===")

    try:
        computador_id, segredo, caminho = localizar_credencial()

        print("\nCredencial encontrada!")
        print("Arquivo:", caminho)
        print("Computador ID:", computador_id)

        usuario = input("\nUsuário administrador: ")
        senha = getpass.getpass("Senha: ")

        resposta = requests.post(
            f"{URL_SERVIDOR}/admin/login",
            json={
                "usuario": usuario,
                "senha": senha
            },
            timeout=15
        )

        resposta.raise_for_status()

        token = resposta.json()["token"]

        cabecalhos = {
            "Authorization": f"Bearer {token}"
        }

        try:
            resposta = requests.post(
                f"{URL_SERVIDOR}/usb/registrar",
                json={
                    "computador_id": computador_id,
                    "segredo_usb": segredo
                },
                headers=cabecalhos,
                timeout=10
            )

            if resposta.status_code == 409:
                print(
                    "\nEste computador já possui uma "
                    "credencial USB registrada."
                )
                return

            resposta.raise_for_status()

            print("\nCredencial registrada com sucesso!")

            print(
                "Agora o servidor possui o hash "
                "da credencial USB."
            )

        finally:
            try:
                requests.post(
                    f"{URL_SERVIDOR}/admin/logout",
                    headers=cabecalhos,
                    timeout=5
                )
            except requests.RequestException:
                pass

    except (
        ValueError,
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        requests.RequestException
    ) as erro:
        print("\nErro:", erro)


if __name__ == "__main__":
    main()
