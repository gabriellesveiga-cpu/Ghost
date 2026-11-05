
import tkinter as tk
from tkinter import messagebox
import getpass

import requests

from janela_conexao import JanelaConexao


URL_SERVIDOR = "http://127.0.0.1:8000"


def iniciar():
    print("=== KEYNEXUS — TESTE DE CONEXÃO ===")

    usuario = input("Usuário administrador: ")
    senha = getpass.getpass("Senha: ")

    try:
        resposta = requests.post(
            f"{URL_SERVIDOR}/admin/login",
            json={
                "usuario": usuario,
                "senha": senha
            },
            timeout=5
        )

        resposta.raise_for_status()
        token = resposta.json()["token"]

    except (requests.RequestException, KeyError) as erro:
        print("Erro no login:", erro)
        return

    janela = tk.Tk()
    janela.withdraw()

    JanelaConexao(janela, token)

    janela.mainloop()

    try:
        requests.post(
            f"{URL_SERVIDOR}/admin/logout",
            headers={
                "Authorization": f"Bearer {token}"
            },
            timeout=5
        )
    except requests.RequestException:
        pass


if __name__ == "__main__":
    iniciar()
