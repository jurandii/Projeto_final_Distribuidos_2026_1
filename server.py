import socket
import sys
import threading
import json
import urllib.request
import urllib.error
from processamento_lento.processamento_lento import despachar_processamento, PermissaoNegadaError
import time
from logs_sistema import obter_logger, registrar_info, registrar_erro
from processamento_lento.processamento_lento import despachar_processamento
main

# SETOR TOLERANCIA A FALHAS: rede de seguranca para erros do lado do servidor.
from tolerancia_falhas import tolerancia_falhas as tf

# =========================================================================
# SETOR: THREADS
# Responsabilidade deste setor: garantir que o servidor atenda MAIS DE UM
# cliente ao mesmo tempo, sem que um cliente bloqueado/lento impeça os
# demais de serem atendidos.
#
# Estrategia adotada:
#   - O socket principal (sock) so faz accept() em loop, na thread principal.
#   - Cada conexao aceita (conn, endereco) ganha a SUA PROPRIA thread,
#     executando atender_cliente(). Assim, o tempo que o servidor gasta
#     conversando com o cliente A nao impede o accept() de um cliente B,
#     nem o atendimento de um cliente C que ja esteja conectado.
#   - threads_ativas / lock_threads servem so para podermos mostrar,
#     a qualquer momento, quantos clientes estao sendo atendidos
#     concorrentemente (Entrega: "Demonstracao de mais de uma atividade
#     acontecendo de forma concorrente").
# =========================================================================

host_address = "127.0.0.1"
port = 40000
logger = obter_logger("servidor")

# ----- controle de threads ativas (so para fins de demonstracao/log) -----
threads_ativas = 0
lock_threads = threading.Lock()


class Produto:
    def __init__(self, nome, valor):
        self.nome = nome
        self.valor = valor


# OBS: os valores abaixo usam "." (ponto) e nao "," (virgula). Em Python,
# Produto("coxinha", 6,00) e LIDO como dois argumentos (6 e 00), o que
# quebra a classe Produto (que so aceita nome, valor). Correcao de sintaxe
# necessaria para o programa simplesmente RODAR -- nao e mudanca de regra
# de negocio, e o item nao compilava antes.
catalogo = [
    Produto("coxinha", 6.00),
    Produto("bolinho", 4.00),
    Produto("rocambole", 12.00),
]


def main():
    sock = socket_start()
    listen(sock)


def socket_start() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host_address, port))
        registrar_info(logger, "socket_iniciado", host=host_address, porta=port)
        return sock
    except OSError as exc:
        registrar_erro(logger, "socket_erro", exc, host=host_address, porta=port)
        print(
            f"[SERVER] Não foi possível usar {host_address}:{port} ({exc}).",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def listen(sock: socket.socket):
    """
    Loop principal: so aceita novas conexoes e delega cada uma para uma
    thread. NAO conversa diretamente com nenhum cliente aqui -- isso fica
    a cargo de atender_cliente(), rodando em paralelo para cada conexao.
    """
    sock.listen(5)

    print(f"[SERVER] Escutando em {host_address}:{port}", flush=True)
    registrar_info(logger, "servidor_escutando", host=host_address, porta=port)
    print(
        "[SERVER] Aguardando clientes (fica parado aqui até um connect) — é normal.",
        flush=True,
    )
    print("[SERVER] Ctrl+C encerra o processo inteiro.\n", flush=True)

    try:
        while True:
            conn, endereco = sock.accept()
            print(f"[SERVER] Cliente conectado: {endereco}")
            registrar_info(logger, "cliente_conectado", cliente=endereco)

            # cada cliente recebe sua propria thread de atendimento.
            # daemon=True garante que essas threads nao impedem o processo
            # de encerrar quando o servidor recebe Ctrl+C.
            thread_cliente = threading.Thread(
                target=atender_cliente,
                args=(conn, endereco),
                daemon=True,
            )
            thread_cliente.start()

    except KeyboardInterrupt:
        registrar_info(logger, "servidor_encerrado_por_usuario")
        print("\n[SERVER] Encerrado.")
    finally:
        registrar_info(logger, "socket_fechado", host=host_address, porta=port)
        sock.close()


def atender_cliente(conn: socket.socket, endereco):
    """
    Roda em uma thread dedicada para CADA cliente conectado. Enquanto esta
    funcao espera dados deste cliente especifico (conn.recv, que bloqueia),
    a thread principal continua livre para aceitar outros clientes, e as
    demais threads de atender_cliente continuam atendendo os seus.
    """
    global threads_ativas

    with lock_threads:
        threads_ativas += 1
        print(f"[SERVER] Threads ativas no momento: {threads_ativas}")
        registrar_info(
            logger,
            "thread_cliente_iniciada",
            cliente=endereco,
            thread=threading.current_thread().name,
            threads_ativas=threads_ativas,
        )

    # TOLERANCIA A FALHAS: timeout de inatividade. Um cliente "pendurado"
    # (travado/morto sem fechar a conexao) nao segura a thread para sempre.
    conn.settimeout(tf.TIMEOUT_INATIVIDADE)

    try:
        while True:
            # --- LEITURA DE REDE ---
            # Este recv() bloqueia apenas a thread atual (a deste cliente).
            # As outras threads (outros clientes) nao sao afetadas.
            data = conn.recv(4096)

            if not data:
                print(f"[SERVER] Cliente {endereco} fechou a conexão.")
                registrar_info(logger, "cliente_fechou_conexao", cliente=endereco)
                break

            texto = data.decode("utf-8", errors="replace").strip()
            print(f"[SERVER] [{endereco}] recebido: {texto!r} "
                  f"(thread={threading.current_thread().name})")
            registrar_info(
                logger,
                "chamada_recebida",
                cliente=endereco,
                thread=threading.current_thread().name,
                bytes_recebidos=len(data),
                mensagem=texto,
            )

            # TOLERANCIA A FALHAS: rejeita mensagens invalidas (ex.: grandes
            # demais) com feedback claro, sem derrubar a conexao.
            try:
                tf.validar_mensagem(texto)
            except tf.RequisicaoInvalidaError as exc:
                registrar_erro(
                    logger,
                    "chamada_rejeitada",
                    exc,
                    cliente=endereco,
                    mensagem=texto,
                )
                tf.registrar_erro(f"server[{endereco}]", exc, "mensagem invalida recebida")
                resposta_erro = tf.formatar_erro(exc.codigo, exc.mensagem_usuario)
                conn.sendall(resposta_erro.encode("utf-8"))
                registrar_info(
                    logger,
                    "resposta_enviada",
                    cliente=endereco,
                    status="erro",
                    codigo=exc.codigo,
                    bytes_enviados=len(resposta_erro.encode("utf-8")),
                )
                continue

            if exit_request(texto):
                resposta_saida = "OK: sessao encerrada no servidor.\n"
                conn.sendall(resposta_saida.encode("utf-8"))
                registrar_info(logger, "sessao_encerrada_pelo_cliente", cliente=endereco)
                print(f"[SERVER] Encerramento pedido pelo cliente {endereco}.")
                break

            # TOLERANCIA A FALHAS: o despacho roda dentro de uma "rede de
            # seguranca". Qualquer excecao nao prevista vira uma resposta de
            # erro padronizada (e registrada em log), em vez de matar esta
            # thread e desconectar o cliente sem explicacao.
            inicio = time.perf_counter()
            resposta = tf.processar_requisicao_segura(
                processar_requisicao, texto, conn, endereco,
                origem=f"server[{endereco}]",
            )
            tempo_ms = (time.perf_counter() - inicio) * 1000
            conn.sendall(resposta.encode("utf-8"))
            registrar_info(
                logger,
                "resposta_enviada",
                cliente=endereco,
                status="erro" if tf.e_resposta_de_erro(resposta) else "sucesso",
                tempo_ms=f"{tempo_ms:.2f}",
                bytes_enviados=len(resposta.encode("utf-8")),
                resumo_resposta=resposta,
            )

    except socket.timeout:
        # Cliente inativo por tempo demais: encerra com feedback e libera a thread.
        tf.registrar_evento(f"server[{endereco}]", "conexao encerrada por inatividade (timeout)")
        registrar_info(logger, "cliente_timeout", cliente=endereco)
        try:
            conn.sendall(
                tf.formatar_erro(tf.ERRO_TIMEOUT, "Conexao encerrada por inatividade.").encode("utf-8")
            )
        except OSError:
            pass
        print(f"[SERVER] {endereco} desconectado por inatividade (timeout).")
    except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
        # Queda abrupta do canal (cliente caiu/foi morto). Registramos e
        # seguimos: as demais threads/clientes continuam funcionando.
        tf.registrar_erro(f"server[{endereco}]", exc, "conexao perdida")
        registrar_erro(logger, "conexao_perdida", exc, cliente=endereco)
        print(f"[SERVER] Conexão com {endereco} perdida ({exc}).")
    except Exception as exc:
        # Ultima barreira: nenhum erro inesperado pode derrubar o servidor
        # sem registro. A thread morre de forma controlada e logada.
        tf.registrar_erro(f"server[{endereco}]", exc, "erro inesperado na thread de atendimento")
        registrar_erro(logger, "thread_cliente_erro_inesperado", exc, cliente=endereco)
        print(f"[SERVER] Erro inesperado ao atender {endereco}: {exc}")
    finally:
        conn.close()
        with lock_threads:
            threads_ativas -= 1
            print(f"[SERVER] Socket de {endereco} fechado. "
                  f"Threads ativas restantes: {threads_ativas}\n")
            registrar_info(
                logger,
                "thread_cliente_finalizada",
                cliente=endereco,
                threads_ativas=threads_ativas,
            )

def buscar_cep(cep: str) -> str:
    """
    SETOR: INTEGRAÇÃO COM APIs (ViaCEP)
    Efetua a busca de endereço de forma síncrona na API do ViaCEP usando a stdlib.
    """
    url = f"https://viacep.com.br/ws/{cep}/json/"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    
    try:
        # Timeout de 8s garante que o servidor não fique esperando indefinidamente
        with urllib.request.urlopen(req, timeout=8) as resp:
            status = resp.getcode()
            if status != 200:
                return f"ERRO_API: servico retornou status {status}"
                
            corpo = resp.read().decode("utf-8")
            dados = json.loads(corpo)
            
            # O ViaCEP responde com HTTP 200 mesmo quando o CEP não existe,
            # então o servidor precisa checar explicitamente o campo "erro"
            if dados.get("erro"):
                return f"ERRO_API: nenhum endereco encontrado para o CEP {cep}"
                
            # Formata os dados de sucesso para exibição amigável no cliente
            resposta_formatada = (
                "ENDERECO ENCONTRADO\n"
                f"Logradouro: {dados.get('logradouro', 'N/A')}\n"
                f"Complemento: {dados.get('complemento', 'N/A')}\n"
                f"Bairro: {dados.get('bairro', 'N/A')}\n"
                f"Cidade: {dados.get('localidade', 'N/A')}\n"
                f"UF: {dados.get('uf', 'N/A')}\n"
            )
            return resposta_formatada
    except Exception as exc:
        return f"ERRO_API: falha ao buscar CEP ({exc})\n"

def processar_requisicao(texto: str, conn: socket.socket, endereco) -> str:
    """
    Ponto unico de despacho das requisicoes que chegam de um cliente.
    Este setor (THREADS) so garante que esta funcao roda de forma
    concorrente para varios clientes -- o CONTEUDO de cada bloco abaixo
    e responsabilidade dos setores indicados nos TODOs.
    """

    # TODO(AUTENTICACAO/PERMISSOES): validar login/usuario antes de
    # processar qualquer comando que exija permissao (ex.: LISTADEITENS,
    # PEDIDO, DEPOSITO). Hoje qualquer cliente conectado pode pedir
    # qualquer coisa.

    # TODO(SEGURANCA): os dados trafegados (texto recebido em 'data') ainda
    # chegam em texto puro. Este setor deve decidir onde a descriptografia
    # entra no fluxo (provavelmente logo apos o recv(), antes do decode
    # acima) e onde a criptografia entra antes do sendall() da resposta.

    # TODO(PROCESSAMENTO LENTO / MULTIPROCESSING): comandos que disparem
    # calculo pesado devem rodar em um Process (multiprocessing), nao
    # diretamente aqui dentro da thread do cliente. Caso contrario, um
    # calculo pesado bloqueia *esta* thread (o que e aceitavel, pois nao
    # afeta as outras threads/clientes), mas ainda assim deixa ESTE
    # cliente parado por muito tempo sem nenhuma resposta parcial.
    # Sugestao: usar concurrent.futures.ProcessPoolExecutor ou
    # multiprocessing.Process e (se quiserem) enviar uma resposta
    # imediata de "processando..." antes do resultado final.

    # TODO(LOGS): registrar aqui (ou via modulo de logging dedicado) quem
    # pediu o que, quando, e qual foi o resultado/erro.

    perfil_mockado = "usuario" #Temporário enquanto o grupo de autenticação não estiver pronto
    if "admin" in texto.lower():
        perfil_mockado = "administrador"

    # -------------------------------------------------------------------------
    # PARSE SIMPLES DE COMANDOS DO SEU SETOR
    # Exemplo de comandos: "CALCULO:SIMULAR_ENTREGA|5" ou "CALCULO:AUDITORIA_VENDAS|20000000"
    # -------------------------------------------------------------------------
    posicao_calculo = texto.upper().find("CALCULO:")
    if posicao_calculo >= 0:
        comando_calculo = texto[posicao_calculo:]
        partes = comando_calculo.split(":", 1)[1].split("|")
        operacao = partes[0]
        parametro = int(partes[1]) if len(partes) > 1 else None

        registrar_info(
            logger,
            "processamento_lento_solicitado",
            cliente=endereco,
            perfil=perfil_mockado,
            operacao=operacao,
            parametro=parametro,
        )

        # Chama o despachador isolado. PermissaoNegadaError deve subir ate
        # tf.processar_requisicao_segura para virar ERRO|ERRO_PERMISSAO|...
        if parametro is not None:
            return despachar_processamento(perfil_mockado, operacao, parametro)
        return despachar_processamento(perfil_mockado, operacao)

    if texto.upper() == "LISTADEITENS":
        # Exemplo simples de resposta a partir do catalogo da BASE.
        linhas = [f"{i} - {p.nome} - R$ {p.valor:.2f}" for i, p in enumerate(catalogo)]
        return "ITENS:\n" + "\n".join(linhas) + "\n"

    return f"DEMO_TCP_OK: recebi sua linha ({len(texto)} caracteres)\n"


def exit_request(texto: str) -> bool:
    t = texto.strip()
    if t.upper() == "CLOSECONNECTION":
        return True
    if "|" in t:
        _, resto = t.split("|", 1)
        if resto.strip().upper() == "CLOSECONNECTION":
            return True
    return False


if __name__ == "__main__":
    main()
