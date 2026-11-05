
import getpass
import json
from pathlib import Path

from autenticacao import gerar_hash_senha


PASTA = Path(__file__).resolve().parent / "dados"
ARQUIVO = PASTA / "administrador.json"


def main():
    PASTA.mkdir(parents=True, exist_ok=True)

    if ARQUIVO.exists():
        print("Administrador já configurado.")
        return

    print("=== KEYNEXUS ===")
    print("Configuração do administrador\n")

    usuario = input("Usuário: ").strip()

    if not usuario:
        print("Usuário inválido.")
        return

    senha = getpass.getpass("Senha: ")
    confirmacao = getpass.getpass("Confirme a senha: ")

    if senha != confirmacao:
        print("As senhas não coincidem.")
        return

    if len(senha) < 12:
        print("Use uma senha de pelo menos 12 caracteres.")
        return

    dados = {
        "usuario": usuario,
        "senha_hash": gerar_hash_senha(senha)
    }

    with open(ARQUIVO, "x", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, indent=4)

    print("\nAdministrador criado com sucesso!")


if __name__ == "__main__":
    main()
