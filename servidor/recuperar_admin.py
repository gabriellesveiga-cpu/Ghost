"""Recuperação local explícita; não importe este módulo em rotas HTTP."""
import ctypes
import getpass
import os
import sys

if __package__:
    from .credenciais_admin import RepositorioAdministrador
else:
    from credenciais_admin import RepositorioAdministrador

CONFIRMACAO = "CONFIRMO RECUPERAR A SENHA LOCAL"


def exigir_ambiente_local():
    if os.name != "nt" or not sys.stdin.isatty() or not sys.stdout.isatty():
        raise PermissionError("Use um console interativo local do Windows.")
    if (os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT")
            or ctypes.windll.user32.GetSystemMetrics(0x1000)):
        raise PermissionError("Recuperação não disponível em sessões remotas reconhecidas.")
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Abra o console local como Administrador autorizado do Windows.")


def main():
    try:
        exigir_ambiente_local()
        if len(sys.argv) != 1:
            raise PermissionError("A recuperação não aceita argumentos de linha de comando.")
        print("Esta operação altera a senha administrativa e invalida os logins anteriores.")
        usuario = input("Usuário administrativo cadastrado: ")
        if input("Digite CONFIRMO RECUPERAR A SENHA LOCAL para continuar: ") != CONFIRMACAO:
            print("Recuperação cancelada; nenhuma alteração realizada.")
            return 1
        # Não admite o fallback do getpass que poderia ecoar a senha.
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            senha = getpass.getpass("Nova senha (15 a 1024 caracteres): ")
            confirmacao = getpass.getpass("Confirme a nova senha: ")
        RepositorioAdministrador().recuperar(usuario, senha, confirmacao)
        print("Recuperação concluída. Entre novamente no Administrador com a nova senha.")
        return 0
    except (PermissionError, ValueError, OSError, EOFError, getpass.GetPassWarning):
        print("Recuperação não realizada. Confira permissão local, usuário e requisitos da nova senha.")
        return 1
    except KeyboardInterrupt:
        print("Recuperação cancelada.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
