import binascii
import hashlib
import secrets


PBKDF2_ITERATIONS = 120_000
PASSWORD_SCHEME = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"{PASSWORD_SCHEME}${PBKDF2_ITERATIONS}${salt}${binascii.hexlify(password_hash).decode('ascii')}"


def is_password_hashed(value: str | None) -> bool:
    return bool(value and value.startswith(f"{PASSWORD_SCHEME}$"))


def verify_password(stored_password: str, candidate_password: str) -> bool:
    if not stored_password:
        return False

    if not is_password_hashed(stored_password):
        return secrets.compare_digest(stored_password, candidate_password)

    try:
        _, iterations, salt, password_hash = stored_password.split("$", 3)
        derived_hash = hashlib.pbkdf2_hmac(
            "sha256",
            candidate_password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
    except (TypeError, ValueError):
        return False

    return secrets.compare_digest(password_hash, binascii.hexlify(derived_hash).decode("ascii"))