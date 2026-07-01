from cryptography.fernet import Fernet

ARQUIVO_CHAVE = "seguranca/chave.key"


def carregar_chave():
    with open(ARQUIVO_CHAVE, "rb") as arquivo:
        return arquivo.read()


fernet = Fernet(carregar_chave())


def criptografar(mensagem: str) -> bytes:
    return fernet.encrypt(mensagem.encode())


def descriptografar(mensagem: bytes) -> str:
    return fernet.decrypt(mensagem).decode()