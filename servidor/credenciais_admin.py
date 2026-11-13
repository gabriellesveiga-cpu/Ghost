"""Persistência e rotação da conta administrativa, sem segredos em logs."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time

try:
    from .autenticacao import gerar_hash_senha, verificar_senha
except ImportError:
    from autenticacao import gerar_hash_senha, verificar_senha

ARQUIVO_ADMIN = Path(__file__).resolve().parent / "dados" / "administrador.json"
_BLOQUEIO = threading.RLock()


class SessaoObsoleta(PermissionError):
    pass


def validar_nova_senha(senha, confirmacao, usuario):
    if not isinstance(senha, str) or not 15 <= len(senha) <= 1024 or not senha.strip():
        raise ValueError("Use uma senha ou frase de 15 a 1024 caracteres.")
    try:
        if not hmac.compare_digest(senha.encode("utf-8"), confirmacao.encode("utf-8")):
            raise ValueError("A confirmação da nova senha é diferente.")
    except (UnicodeError, AttributeError):
        raise ValueError("Nova senha ou confirmação inválida.") from None
    comuns = {"123456789012345", "1234567890123456", "passwordpassword",
              "administrador123", "senhasenhasenha123", "qwertyuiopasdfgh"}
    if (senha.casefold() in comuns or senha.casefold() == usuario.casefold()
            or len(set(senha)) == 1):
        raise ValueError("Escolha uma senha menos previsível.")


def versao_credencial(registro):
    # Compatível com cadastros antigos; mudar hash ou versão invalida tokens.
    dados = [registro["usuario"], registro["senha_hash"], registro.get("versao_credencial")]
    return hashlib.sha256(json.dumps(dados, ensure_ascii=True).encode()).hexdigest()


class RepositorioAdministrador:
    def __init__(self, caminho=ARQUIVO_ADMIN, timeout=5):
        self.caminho = Path(caminho)
        self.timeout = timeout

    @contextmanager
    def bloquear(self):
        if not _BLOQUEIO.acquire(timeout=self.timeout):
            raise TimeoutError("Credenciais temporariamente ocupadas.")
        try:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            # O arquivo de lock fica estável; não é removido entre operações.
            with self.caminho.with_suffix(".lock").open("a+b") as arquivo:
                if os.fstat(arquivo.fileno()).st_size == 0:
                    arquivo.write(b"\0")
                    arquivo.flush()
                limite = time.monotonic() + self.timeout
                while True:
                    try:
                        arquivo.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= limite:
                            raise TimeoutError("Credenciais temporariamente ocupadas.") from None
                        time.sleep(0.02)
                try:
                    yield
                finally:
                    arquivo.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(arquivo.fileno(), fcntl.LOCK_UN)
        finally:
            _BLOQUEIO.release()

    def ler(self):
        try:
            with self.caminho.open("r", encoding="utf-8") as arquivo:
                registro = json.load(arquivo)
        except FileNotFoundError:
            return None
        if (not isinstance(registro, dict) or not isinstance(registro.get("usuario"), str)
                or not registro["usuario"] or not isinstance(registro.get("senha_hash"), str)):
            raise ValueError("Cadastro administrativo inválido.")
        return registro

    def _gravar(self, registro):
        temporario = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.caminho.parent,
                prefix=".administrador-", suffix=".tmp", delete=False
            ) as arquivo:
                temporario = Path(arquivo.name)
                json.dump(registro, arquivo, ensure_ascii=True, indent=4)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            os.replace(temporario, self.caminho)
        finally:
            if temporario is not None and temporario.exists():
                temporario.unlink()

    def _atualizar(self, registro, nova_senha, confirmacao, autorizar=None):
        validar_nova_senha(nova_senha, confirmacao, registro["usuario"])
        if verificar_senha(nova_senha, registro["senha_hash"]):
            raise ValueError("A nova senha deve ser diferente da atual.")
        novo = dict(registro)
        novo.update(senha_hash=gerar_hash_senha(nova_senha),
                    versao_credencial=secrets.token_hex(16),
                    senha_alterada_em=datetime.now(timezone.utc).isoformat())
        if autorizar is not None and not autorizar():
            raise SessaoObsoleta("Sessão administrativa não está mais válida.")
        self._gravar(novo)
        return versao_credencial(novo)

    def trocar(self, senha_atual, nova_senha, confirmacao, versao_esperada, autorizar=None):
        with self.bloquear():
            registro = self.ler()
            if registro is None:
                raise ValueError("Administrador não configurado.")
            if not hmac.compare_digest(versao_credencial(registro), versao_esperada):
                raise SessaoObsoleta("Credencial administrativa já foi alterada.")
            if autorizar is not None and not autorizar():
                raise SessaoObsoleta("Sessão administrativa não está mais válida.")
            if not verificar_senha(senha_atual, registro["senha_hash"]):
                raise PermissionError("Senha atual incorreta.")
            return self._atualizar(registro, nova_senha, confirmacao, autorizar)

    def recuperar(self, usuario, nova_senha, confirmacao):
        # Chamado apenas pela ferramenta local, nunca por uma rota HTTP.
        with self.bloquear():
            registro = self.ler()
            if registro is None:
                raise ValueError("Administrador não configurado. Use a configuração inicial.")
            if not hmac.compare_digest(usuario.encode("utf-8"), registro["usuario"].encode("utf-8")):
                raise PermissionError("Usuário administrativo não confere.")
            return self._atualizar(registro, nova_senha, confirmacao)
