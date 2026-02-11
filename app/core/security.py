"""Security utilities (passwords, JWT). Placeholder for auth layer."""

from passlib.context import CryptContext

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return password_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return password_context.verify(plain, hashed)
