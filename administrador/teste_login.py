
import getpass
import requests

URL = "http://127.0.0.1:8000"

print("=== KEYNEXUS — TESTE DE LOGIN ===")

usuario = input("Usuário: ")
senha = getpass.getpass("Senha: ")

try:
    # Teste sem autenticação
    resposta = requests.get(
        f"{URL}/computadores",
        timeout=5
    )

    print(
        "\nAcesso sem login:",
        resposta.status_code
    )

    # Login administrativo
    resposta = requests.post(
        f"{URL}/admin/login",
        json={
            "usuario": usuario,
            "senha": senha
        },
        timeout=10
    )

    resposta.raise_for_status()

    dados = resposta.json()
    token = dados["token"]

    print("Login realizado com sucesso!")

    cabecalhos = {
        "Authorization": f"Bearer {token}"
    }

    # Consulta autenticada
    resposta = requests.get(
        f"{URL}/computadores",
        headers=cabecalhos,
        timeout=5
    )

    resposta.raise_for_status()

    print(
        "Acesso autorizado:",
        resposta.status_code
    )

    print(
        "Computadores cadastrados:",
        resposta.json()["total"]
    )

    # Encerrar sessão
    resposta = requests.post(
        f"{URL}/admin/logout",
        headers=cabecalhos,
        timeout=5
    )

    resposta.raise_for_status()

    print("Logout realizado!")

    # Verificar que o token foi invalidado
    resposta = requests.get(
        f"{URL}/computadores",
        headers=cabecalhos,
        timeout=5
    )

    print(
        "Acesso após logout:",
        resposta.status_code
    )

except requests.RequestException as erro:
    print("\nErro:", erro)
