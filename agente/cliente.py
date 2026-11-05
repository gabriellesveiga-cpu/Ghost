
import requests

URL_SERVIDOR = "http://127.0.0.1:8000"


def verificar_servidor():
    try:
        resposta = requests.get(
            f"{URL_SERVIDOR}/status",
            timeout=5
        )

        resposta.raise_for_status()

        dados = resposta.json()

        print("Conexão estabelecida!")
        print("Servidor:", dados["servidor"])
        print("Versão:", dados["versao"])

    except requests.RequestException as erro:
        print("Não foi possível conectar ao servidor.")
        print("Erro:", erro)


if __name__ == "__main__":
    verificar_servidor()

