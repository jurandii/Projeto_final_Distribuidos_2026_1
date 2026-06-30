"""
=============================================================================
SETOR: TOLERANCIA A FALHAS  (Jose, Nicola e Guilherme)
=============================================================================

Responsabilidade deste setor: tratar o maior numero possivel de falhas para
que o produto continue integro para o usuario, dando feedback claro quando
algo der errado e GARANTINDO QUE O PROGRAMA NAO ENCERRE diante de um erro de
processo ou de canal.

Este modulo NAO implementa regra de negocio de nenhum outro setor. Ele oferece
"ferramentas de resiliencia" reutilizaveis que o servidor, o cliente e o setor
de APIs externas podem usar para:

  - tratar erros do lado do servidor sem derrubar a thread do cliente;
  - tratar erros do lado do cliente sem encerrar o programa com traceback;
  - dar feedback adequado ao usuario (protocolo padronizado "ERRO|CODIGO|msg");
  - tratar conexao recusada/perdida, mensagem invalida, timeout, usuario sem
    permissao e indisponibilidade de APIs externas;
  - registrar todos os erros em log.

Compatibilidade: escrito para rodar de Python 3.9 ate 3.12+ (evita match/case
e anotacoes "X | None"), pois o restante do projeto roda em 3.12.
=============================================================================
"""

import os
import time
import socket
import logging
from typing import Callable, Optional, Tuple

# =============================================================================
# 1) PROTOCOLO PADRONIZADO DE ERRO
# -----------------------------------------------------------------------------
# Toda falha tratada e devolvida ao cliente no formato:
#       ERRO|<CODIGO>|<mensagem legivel para o usuario>\n
# Assim o cliente consegue detectar de forma simples que veio um erro e exibir
# uma mensagem amigavel, em vez de um traceback ou uma resposta crua.
# =============================================================================

PREFIXO_ERRO = "ERRO"
SEPARADOR = "|"

# Codigos de erro previstos (cobrem as falhas exigidas pelo setor).
ERRO_CONEXAO = "ERRO_CONEXAO"
ERRO_TIMEOUT = "ERRO_TIMEOUT"
ERRO_REQUISICAO_INVALIDA = "ERRO_REQUISICAO_INVALIDA"
ERRO_PERMISSAO = "ERRO_PERMISSAO"
ERRO_API_EXTERNA = "ERRO_API_EXTERNA"
ERRO_INTERNO = "ERRO_INTERNO"

# Mensagem amigavel padrao para cada codigo (usada quando o chamador nao
# fornece uma mensagem especifica).
MENSAGENS_PADRAO = {
    ERRO_CONEXAO: "Nao foi possivel falar com o servidor (canal indisponivel).",
    ERRO_TIMEOUT: "O servidor demorou demais para responder (timeout).",
    ERRO_REQUISICAO_INVALIDA: "A requisicao enviada e invalida ou esta mal formada.",
    ERRO_PERMISSAO: "Voce nao tem permissao para executar esta operacao.",
    ERRO_API_EXTERNA: "Um servico externo esta indisponivel no momento. Tente mais tarde.",
    ERRO_INTERNO: "Ocorreu um erro interno no servidor. A operacao foi cancelada com seguranca.",
}


# =============================================================================
# 2) EXCECOES DA APLICACAO
# -----------------------------------------------------------------------------
# Excecoes "conhecidas". Quando qualquer parte do sistema levantar uma destas,
# o setor de tolerancia a falhas sabe exatamente qual codigo e qual mensagem
# devolver ao usuario.
# =============================================================================


class ErroAplicacao(Exception):
    """
    Erro tratado da aplicacao. Carrega um codigo do protocolo, uma mensagem
    amigavel ao usuario e, opcionalmente, um detalhe tecnico (que vai apenas
    para o log, nunca para o usuario, evitando vazar informacao sensivel).
    """

    def __init__(self, codigo, mensagem_usuario=None, detalhe=None):
        self.codigo = codigo
        self.mensagem_usuario = mensagem_usuario or MENSAGENS_PADRAO.get(
            codigo, MENSAGENS_PADRAO[ERRO_INTERNO]
        )
        self.detalhe = detalhe
        super().__init__(self.mensagem_usuario)


class RequisicaoInvalidaError(ErroAplicacao):
    def __init__(self, mensagem_usuario=None, detalhe=None):
        super().__init__(ERRO_REQUISICAO_INVALIDA, mensagem_usuario, detalhe)


class PermissaoError(ErroAplicacao):
    def __init__(self, mensagem_usuario=None, detalhe=None):
        super().__init__(ERRO_PERMISSAO, mensagem_usuario, detalhe)


class ErroAPIExterna(ErroAplicacao):
    def __init__(self, mensagem_usuario=None, detalhe=None):
        super().__init__(ERRO_API_EXTERNA, mensagem_usuario, detalhe)


# =============================================================================
# 3) SISTEMA DE LOG DE ERROS
# -----------------------------------------------------------------------------
# Requisito do setor: "Garantir que erros sejam registrados nos logs".
# Usamos um logger PROPRIO e nomeado ("tolerancia_falhas"), com handler de
# arquivo + handler de stderr. Nao mexemos no logging raiz para nao conflitar
# com o que o setor de LOGS venha a configurar depois.
# Caminho do arquivo configuravel por TF_LOG_FILE.
# =============================================================================

_PASTA_LOG_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
_ARQUIVO_LOG = os.environ.get(
    "TF_LOG_FILE", os.path.join(_PASTA_LOG_PADRAO, "tolerancia_falhas.log")
)

_logger = None  # cache do logger ja configurado


def _obter_logger():
    """Cria/recupera o logger do setor. A configuracao acontece uma unica vez."""
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("tolerancia_falhas")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # nao polui o root logger

    # Se ja tem handlers (re-import em testes), nao duplica.
    if not logger.handlers:
        formato = logging.Formatter(
            "%(asctime)s [%(levelname)s] [TOLERANCIA] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Handler de arquivo (best-effort: se falhar, seguimos so com stderr,
        # pois o sistema de log NAO pode derrubar a aplicacao).
        try:
            os.makedirs(os.path.dirname(_ARQUIVO_LOG), exist_ok=True)
            fh = logging.FileHandler(_ARQUIVO_LOG, encoding="utf-8")
            fh.setFormatter(formato)
            logger.addHandler(fh)
        except OSError:
            pass

        # Handler de tela (stderr) para acompanhar em tempo real.
        sh = logging.StreamHandler()
        sh.setFormatter(formato)
        logger.addHandler(sh)

    _logger = logger
    return logger


def registrar_erro(origem, excecao, contexto=""):
    """
    Registra um erro no log. 'origem' identifica de onde veio (ex.:
    "server[('127.0.0.1', 5050)]" ou "cliente.listen"). Nunca lanca excecao.
    """
    try:
        logger = _obter_logger()
        detalhe = getattr(excecao, "detalhe", None)
        partes = [f"origem={origem}", f"tipo={type(excecao).__name__}", f"erro={excecao}"]
        if contexto:
            partes.append(f"contexto={contexto}")
        if detalhe:
            partes.append(f"detalhe={detalhe}")
        logger.error(" | ".join(partes))
    except Exception:
        # Logar NUNCA pode quebrar o fluxo principal.
        pass


def registrar_evento(origem, mensagem):
    """Registra um evento informativo (ex.: tentativa de reconexao, timeout)."""
    try:
        _obter_logger().info(f"origem={origem} | {mensagem}")
    except Exception:
        pass


# =============================================================================
# 4) FORMATACAO / INTERPRETACAO DAS RESPOSTAS DE ERRO
# =============================================================================


def formatar_erro(codigo, mensagem=None):
    """Monta a resposta de erro no formato do protocolo: ERRO|CODIGO|msg\\n"""
    if mensagem is None:
        mensagem = MENSAGENS_PADRAO.get(codigo, MENSAGENS_PADRAO[ERRO_INTERNO])
    # remove quebras de linha do meio da mensagem para nao baguncar o protocolo
    mensagem = str(mensagem).replace("\n", " ").strip()
    return f"{PREFIXO_ERRO}{SEPARADOR}{codigo}{SEPARADOR}{mensagem}\n"


def e_resposta_de_erro(texto):
    """True se 'texto' for uma resposta de erro do protocolo (ERRO|...|...)."""
    if not isinstance(texto, str):
        return False
    return texto.strip().startswith(PREFIXO_ERRO + SEPARADOR)


def descrever_erro_para_usuario(texto):
    """
    Converte 'ERRO|CODIGO|mensagem' em uma frase amigavel para mostrar ao
    usuario no cliente. Se nao conseguir interpretar, devolve o texto cru.
    """
    if not e_resposta_de_erro(texto):
        return texto
    partes = texto.strip().split(SEPARADOR, 2)
    if len(partes) == 3:
        _, codigo, mensagem = partes
        return f"{mensagem} (codigo: {codigo})"
    return texto.strip()


# =============================================================================
# 5) TRADUCAO DE EXCECAO -> (codigo, mensagem)
# -----------------------------------------------------------------------------
# Coracao do setor: pega QUALQUER excecao (inclusive de outros setores) e a
# transforma em um par (codigo, mensagem amigavel). Nao acopla import de
# outros modulos: erros de permissao de outros setores sao detectados pelo
# nome da classe.
# =============================================================================


def traduzir_excecao(excecao):
    # type: (BaseException) -> Tuple[str, str]
    if isinstance(excecao, ErroAplicacao):
        return excecao.codigo, excecao.mensagem_usuario

    nome = type(excecao).__name__.lower()

    # socket.timeout em 3.10+ e alias de TimeoutError; cobrimos os dois.
    if isinstance(excecao, (socket.timeout, TimeoutError)):
        return ERRO_TIMEOUT, MENSAGENS_PADRAO[ERRO_TIMEOUT]

    if isinstance(excecao, (ConnectionError, BrokenPipeError)):
        return ERRO_CONEXAO, MENSAGENS_PADRAO[ERRO_CONEXAO]

    # Erros de permissao de outros setores (ex.: PermissaoNegadaError do setor
    # de Processamento Lento) sao reconhecidos pelo nome, sem precisar importar.
    if "permiss" in nome:
        return ERRO_PERMISSAO, MENSAGENS_PADRAO[ERRO_PERMISSAO]

    # Entradas mal formadas: parse de int, indice, chave, decodificacao.
    if isinstance(excecao, (ValueError, IndexError, KeyError, TypeError, UnicodeError)):
        return ERRO_REQUISICAO_INVALIDA, MENSAGENS_PADRAO[ERRO_REQUISICAO_INVALIDA]

    # Qualquer outra coisa inesperada vira erro interno controlado.
    return ERRO_INTERNO, MENSAGENS_PADRAO[ERRO_INTERNO]


# =============================================================================
# 6) LADO SERVIDOR: EXECUCAO SEGURA + VALIDACAO
# =============================================================================

# Timeout de inatividade do socket de cada cliente (em segundos).
# Configuravel por TF_TIMEOUT_INATIVIDADE. "0"/""/"none" => sem timeout.
# Padrao alto (300s) para nao atrapalhar uma demonstracao normal; nos testes
# usamos um valor baixo via variavel de ambiente para provar o tratamento.
def _ler_timeout_inatividade():
    # type: () -> Optional[float]
    bruto = os.environ.get("TF_TIMEOUT_INATIVIDADE", "300").strip().lower()
    if bruto in ("", "0", "none", "nenhum"):
        return None
    try:
        valor = float(bruto)
        return valor if valor > 0 else None
    except ValueError:
        return 300.0


TIMEOUT_INATIVIDADE = _ler_timeout_inatividade()

TAMANHO_MAXIMO_MENSAGEM = 8192


def validar_mensagem(texto, tamanho_maximo=TAMANHO_MAXIMO_MENSAGEM):
    """
    Valida uma mensagem recebida. Levanta RequisicaoInvalidaError se for
    obviamente invalida (None ou grande demais). NAO rejeita string vazia,
    para nao alterar o protocolo ja existente dos outros setores.
    """
    if texto is None:
        raise RequisicaoInvalidaError("Mensagem vazia recebida.", detalhe="texto=None")
    if len(texto) > tamanho_maximo:
        raise RequisicaoInvalidaError(
            "A mensagem enviada e grande demais e foi rejeitada.",
            detalhe=f"tamanho={len(texto)} > maximo={tamanho_maximo}",
        )
    return texto


def processar_requisicao_segura(func, *args, **kwargs):
    """
    REDE DE SEGURANCA DO SERVIDOR.

    Executa 'func(*args, **kwargs)' (tipicamente o despachador de comandos do
    setor BASE) e GARANTE que nenhuma excecao escape: qualquer erro vira uma
    resposta de erro padronizada, registrada no log. Assim, a thread que
    atende o cliente NUNCA morre por uma excecao nao tratada.

    Aceita o parametro nomeado 'origem' para identificar o cliente no log.
    Sempre devolve uma string pronta para enviar ao cliente.
    """
    origem = kwargs.pop("origem", "servidor")
    try:
        resultado = func(*args, **kwargs)
        return resultado if isinstance(resultado, str) else str(resultado)
    except ErroAplicacao as exc:
        registrar_erro(origem, exc, "erro de aplicacao tratado")
        return formatar_erro(exc.codigo, exc.mensagem_usuario)
    except Exception as exc:  # rede de seguranca: pega TUDO
        codigo, mensagem = traduzir_excecao(exc)
        registrar_erro(origem, exc, "excecao capturada pela rede de seguranca")
        return formatar_erro(codigo, mensagem)


# =============================================================================
# 7) ENVIO / RECEBIMENTO RESILIENTES (uteis para cliente e servidor)
# =============================================================================


def enviar_seguro(conexao, dados, origem="rede"):
    """
    Envia dados sem deixar uma falha de canal derrubar o programa. Aceita str
    ou bytes. Retorna True se enviou, False se o canal falhou (e ja registra
    o erro no log).
    """
    if isinstance(dados, str):
        dados = dados.encode("utf-8")
    try:
        conexao.sendall(dados)
        return True
    except (BrokenPipeError, ConnectionError, OSError) as exc:
        registrar_erro(origem, exc, "falha ao enviar dados pelo canal")
        return False


def receber_seguro(conexao, bufsize=4096, origem="rede"):
    """
    Recebe dados tratando timeout e quedas de canal. Levanta ErroAplicacao
    (ERRO_TIMEOUT / ERRO_CONEXAO) para o chamador decidir o que fazer, ja
    tendo registrado o problema no log.
    """
    try:
        return conexao.recv(bufsize)
    except socket.timeout as exc:
        registrar_evento(origem, "timeout ao aguardar dados")
        raise ErroAplicacao(ERRO_TIMEOUT, detalhe=str(exc))
    except (ConnectionError, OSError) as exc:
        registrar_erro(origem, exc, "falha ao receber dados do canal")
        raise ErroAplicacao(ERRO_CONEXAO, detalhe=str(exc))


# =============================================================================
# 8) LADO CLIENTE: CONEXAO COM RETENTATIVA
# =============================================================================


def conectar_com_retentativa(host, port, tentativas=3, intervalo=1.0, timeout_conexao=5.0):
    """
    Tenta conectar varias vezes antes de desistir, com feedback claro a cada
    tentativa. Em caso de sucesso, devolve o socket em modo BLOQUEANTE (o
    timeout so vale para o connect, nao para o uso posterior). Esgotadas as
    tentativas, levanta ErroAplicacao(ERRO_CONEXAO).
    """
    ultima_exc = None
    for tentativa in range(1, tentativas + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(timeout_conexao)
            s.connect((host, port))
            s.settimeout(None)  # volta ao modo bloqueante para o loop de escuta
            registrar_evento("cliente.conexao", f"conectado a {host}:{port} (tentativa {tentativa})")
            return s
        except (ConnectionRefusedError, socket.timeout, TimeoutError, OSError) as exc:
            ultima_exc = exc
            try:
                s.close()
            except OSError:
                pass
            registrar_evento(
                "cliente.conexao", f"tentativa {tentativa}/{tentativas} falhou: {exc}"
            )
            print(
                f"[CLIENTE] Falha ao conectar em {host}:{port} "
                f"(tentativa {tentativa}/{tentativas}): {exc}"
            )
            if tentativa < tentativas:
                time.sleep(intervalo)

    registrar_erro("cliente.conexao", ultima_exc, "esgotadas as tentativas de conexao")
    raise ErroAplicacao(
        ERRO_CONEXAO,
        "Nao foi possivel conectar ao servidor. Verifique se ele esta no ar e tente novamente.",
        detalhe=str(ultima_exc),
    )


# =============================================================================
# 9) CHAMADA RESILIENTE A APIS EXTERNAS
# -----------------------------------------------------------------------------
# Ferramenta para o setor de APIs EXTERNAS: envolve QUALQUER funcao que faca a
# chamada HTTP e adiciona retentativa, registro em log e tratamento de
# indisponibilidade. Nao depende de bibliotecas externas (so stdlib), entao
# funciona com urllib, requests ou qualquer cliente HTTP que o setor escolher.
# =============================================================================

_SEM_FALLBACK = object()  # sentinela: distingue "sem fallback" de "fallback=None"


def chamar_api_externa(
    func,                  # type: Callable
    *args,
    tentativas=3,
    intervalo=0.5,
    fallback=_SEM_FALLBACK,
    nome_api="api_externa",
    **kwargs
):
    """
    Executa 'func(*args, **kwargs)' (a chamada HTTP do setor de APIs) com
    resiliencia:

      - tenta ate 'tentativas' vezes, com 'intervalo' segundos entre elas;
      - registra cada falha no log;
      - se todas falharem e 'fallback' tiver sido informado, devolve o fallback
        (degrada com elegancia, sem quebrar o cliente);
      - se nenhum fallback foi informado, levanta ErroAPIExterna.

    Retorna o que 'func' retornar em caso de sucesso.
    """
    ultima_exc = None
    for tentativa in range(1, tentativas + 1):
        try:
            resultado = func(*args, **kwargs)
            registrar_evento(nome_api, f"chamada externa OK (tentativa {tentativa})")
            return resultado
        except Exception as exc:  # qualquer erro de rede/HTTP/parse
            ultima_exc = exc
            registrar_erro(
                nome_api, exc, f"falha na chamada externa (tentativa {tentativa}/{tentativas})"
            )
            if tentativa < tentativas:
                time.sleep(intervalo)

    if fallback is not _SEM_FALLBACK:
        registrar_evento(nome_api, "todas as tentativas falharam; usando fallback")
        return fallback

    raise ErroAPIExterna(
        f"O servico '{nome_api}' esta indisponivel no momento. Tente novamente mais tarde.",
        detalhe=str(ultima_exc),
    )
