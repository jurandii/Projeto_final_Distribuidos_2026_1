import json

TAMANHO_MAXIMO = 4096


def validar_tamanho(dados):

    if len(dados) > TAMANHO_MAXIMO:
        return False

    return True


def validar_json(texto):

    try:
        json.loads(texto)
        return True

    except Exception:
        return False


def validar_comando(comando):

    comandos = [

        "login",
        "logout",
        "soma",
        "media",
        "primos",
        "tempo",
        "api"

    ]

    return comando in comandos


def limpar_texto(texto):

    proibidos = [

        ";",
        "--",
        "<",
        ">",
        "\\",
        "'",
        "\""

    ]

    for item in proibidos:

        texto = texto.replace(item, "")

    return texto