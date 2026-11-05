
import requests

URL = "http://127.0.0.1:8000"

try:
    print("=== KEYNEXUS ===")

    # Cadastrar computador de teste
    resposta = requests.post(
        f"{URL}/computadores",
        json={
            "nome": "Computador de Teste",
            "tipo": "agente"
        },
        timeout=5
    )

    resposta.raise_for_status()
    cadastro = resposta.json()

    identificador = cadastro["id"]
    chave = cadastro["chave"]

    print("\nComputador cadastrado.")

    # Testar chave correta
    resposta = requests.post(
        f"{URL}/autenticar",
        json={
            "id": identificador,
            "chave": chave
        },
        timeout=5
    )

    resposta.raise_for_status()

    print(
        "Autenticação válida:",
        resposta.json()["autenticado"]
    )

    # Testar chave incorreta
    resposta = requests.post(
        f"{URL}/autenticar",
        json={
            "id": identificador,
            "chave": "chave-incorreta"
        },
        timeout=5
    )

    if resposta.status_code == 401:
        print("Chave incorreta rejeitada corretamente.")
    else:
        print(
            "Resultado inesperado:",
            resposta.status_code
        )

except requests.RequestException as erro:
    print("Erro:", erro)
