from passlib.context import CryptContext
from jose import jwt
import time

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def create_token(data: dict):
    payload = data.copy()
    payload["exp"] = time.time() + 3600
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)