import json
import hashlib

# =========================================================================
# SETOR 5: AUTENTICACAO, USUARIOS E PERMISSOES
# Responsabilidade: Armazenamento e validação de credenciais via hash SHA256.
# =========================================================================

# Estrutura em formato JSON estrito conforme as regras do projeto
USUARIOS_JSON = """
{
  "usuarios": [
    {
      "usuario": "admin",
      "senha_hash": "240be518fabd2724a9fe4296bd69dd9e2cf1e68247ae53d31f4f28ad09364bf1",
      "algoritmo_hash": "sha256",
      "perfil": "administrador",
      "permissoes": ["basico", "avancado"]
    },
    {
      "usuario": "aluno",
      "senha_hash": "d865a016a823f9cbb902bd6307c62bff46a6c7fe31f46f1aee5b1b4a9aa0b5b0",
      "algoritmo_hash": "sha256",
      "perfil": "usuario",
      "permissoes": ["basico"]
    }
  ]
}
"""

def verificar_credenciais(usuario, senha_plana) -> tuple[bool, str]:
    """
    Carrega a base JSON nativamente e valida se o hash da senha
    informada coincide com o registro guardado.
    """
    try:
        base_dados = json.loads(USUARIOS_JSON)
        # Transforma a senha em texto puro no hash correspondente
        hash_calculado = hashlib.sha256(senha_plana.encode("utf-8")).hexdigest()
        
        for registro in base_dados["usuarios"]:
            if registro["usuario"] == usuario and registro["senha_hash"] == hash_calculado:
                return True, registro["perfil"]
    except Exception:
        pass
    return False, ""