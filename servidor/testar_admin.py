
import getpass
import json
from pathlib import Path

from autenticacao import verificar_senha


ARQUIVO = (
    Path(__file__).resolve().parent
    / "dados"
    / "administrador.json"
)


def main():
    if not ARQUIVO.exists():
        print("Administrador não configurado.")
        return

    with open(ARQUIVO, "r", encoding="utf-8") as arquivo:
        administrador = json.load(arquivo)

    usuario = input("Usuário: ").strip()
    senha = getpass.getpass("Senha: ")

    usuario_correto = (
        usuario == administrador["usuario"]
    )

    senha_correta = verificar_senha(
        senha,
        administrador["senha_hash"]
    )

    if usuario_correto and senha_correta:
        print("Autenticação administrativa válida!")
    else:
        print("Usuário ou senha incorretos.")


if __name__ == "__main__":
    main()

