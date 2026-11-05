
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
    return hmac.compare_digest(
        gerar_hash(chave),
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
    try:
        salt_hex, hash_hex = registro.split(":", 1)

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
