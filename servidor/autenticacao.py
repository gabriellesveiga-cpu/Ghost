
import hashlib
import hmac
import secrets


def gerar_chave():
    return secrets.token_urlsafe(32)


def gerar_hash(chave):
    return hashlib.sha256(
        chave.encode("utf-8")
    ).hexdigest()


def verificar_chave(chave, hash_salvo):
    if (not isinstance(chave, str) or not isinstance(hash_salvo, str)
            or len(hash_salvo) != 64
            or any(c not in "0123456789abcdef" for c in hash_salvo)):
        return False
    try:
        hash_recebido = gerar_hash(chave)
    except UnicodeError:
        return False
    return hmac.compare_digest(
        hash_recebido,
        hash_salvo
    )


def gerar_hash_senha(senha):
    salt = secrets.token_bytes(16)

    derivado = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt,
        600_000
    )

    return f"{salt.hex()}:{derivado.hex()}"


def verificar_senha(senha, registro):
    if not isinstance(senha, str) or not isinstance(registro, str):
        return False
    try:
        salt_hex, hash_hex = registro.split(":", 1)
        if len(salt_hex) != 32 or len(hash_hex) != 64:
            return False

        salt = bytes.fromhex(salt_hex)
        esperado = bytes.fromhex(hash_hex)

        recebido = hashlib.pbkdf2_hmac(
            "sha256",
            senha.encode("utf-8"),
            salt,
            600_000
        )

        return hmac.compare_digest(recebido, esperado)

    except (ValueError, TypeError):
        return False
