"""
Módulo de Segurança

Responsável pela criptografia, descriptografia e validação
das mensagens trocadas entre cliente e servidor.
"""

from .criptografia import criptografar, descriptografar
from .validacao import (
    validar_tamanho,
    validar_json,
    validar_comando,
    limpar_texto,
)

__all__ = [
    "criptografar",
    "descriptografar",
    "validar_tamanho",
    "validar_json",
    "validar_comando",
    "limpar_texto",
]