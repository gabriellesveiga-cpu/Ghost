
import requests

URL_SERVIDOR = "http://127.0.0.1:8000"


def cadastrar(nome, tipo):
    resposta = requests.post(
        f"{URL_SERVIDOR}/computadores",
        json={
            "nome": nome,
            "tipo": tipo
        },
        timeout=5
    )

    resposta.raise_for_status()
    return resposta.json()


def listar():
    resposta = requests.get(
        f"{URL_SERVIDOR}/computadores",
        timeout=5
    )

    resposta.raise_for_status()
    return resposta.json()


try:
    print("=== KEYNEXUS ===")

    admin = cadastrar(
        "Computador Administrador",
        "administrador"
    )

    print("\nAdministrador cadastrado!")
    print("ID:", admin["computador"]["id"])

    agente = cadastrar(
        "Computador Remoto",
        "agente"
    )

    print("\nAgente cadastrado!")
    print("ID:", agente["computador"]["id"])

    dados = listar()

    print("\nComputadores cadastrados:")

    for computador in dados["computadores"]:
        print(
            computador["nome"],
            "|",
            computador["tipo"],
            "|",
            computador["status"]
        )

except requests.RequestException as erro:
    print("\nErro de comunicação:")
    print(erro)
