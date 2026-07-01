# PRIMEIRO INSTALE A BIBLIOTECA pip install cryptography

from cryptography.fernet import Fernet

chave = Fernet.generate_key()

with open("chave.key", "wb") as arquivo:
    arquivo.write(chave)

print("Chave criada com sucesso!")