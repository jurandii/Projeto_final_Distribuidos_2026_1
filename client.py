import socket
import sys
import threading
import queue

# SETOR TOLERANCIA A FALHAS: conexao resiliente, feedback claro de erro e
# protecao contra encerramento abrupto do cliente.
from tolerancia_falhas import tolerancia_falhas as tf

# =========================================================================
# SETOR: THREADS
# Responsabilidade deste setor: impedir que o cliente fique bloqueado
# esperando o servidor responder enquanto o usuario tenta digitar algo,
# e impedir que o input() do usuario atrase a exibicao de mensagens que
# o servidor ja mandou.
#
# Estrategia adotada (a "mais robusta", com fila entre threads):
#   - thread_recebe: SO fica em loop fazendo conn.recv() e empilhando
#     cada mensagem recebida na fila_recebidas.
#   - thread principal (main): cuida do menu/input() do usuario e, ANTES
#     de cada pergunta, drena a fila_recebidas para mostrar na tela tudo
#     que chegou do servidor nesse meio tempo.
#   - fila_recebidas (queue.Queue): e thread-safe por padrao, entao nao
#     precisamos de lock manual para passar dados entre as duas threads.
#   - connected (threading.Event): flag thread-safe usada para as duas
#     threads saberem, sem condicao de corrida, quando a conexao deve
#     ser finalizada (substitui o antigo "global connected" que so tinha
#     instrucoes invalidas como "not connected" -- isso nao alterava
#     variavel nenhuma, so calculava um booleano e descartava).
# =========================================================================

server_address = "127.0.0.1"
port = 40000

sock: socket.socket | None = None
fila_recebidas: "queue.Queue[str]" = queue.Queue()
conectado = threading.Event()


class Produto:
    def __init__(self, nome, valor):
        self.nome = nome
        self.valor = valor


# Mesma correcao de sintaxe feita no server.py: "," -> "." nos valores
# (6,00 era lido como dois argumentos posicionais, o que quebra Produto()).
catalogo = [
    Produto("coxinha", 6.00),
    Produto("bolinho", 4.00),
    Produto("rocambole", 12.00),
]


def main():
    global sock

    sock = try_connection()
    conectado.set()  # liga a flag "estamos conectados"

    # Thread dedicada so para escutar o servidor. Roda em paralelo com o
    # menu (que fica na thread principal, lidando com input() do usuario).
    thread_recebe = threading.Thread(target=listen, daemon=True)
    thread_recebe.start()

    # TOLERANCIA A FALHAS: o menu roda dentro de uma protecao. Se o canal
    # cair no meio de uma operacao (servidor morto, conexao perdida) ou se o
    # usuario apertar Ctrl+C, o cliente NAO encerra com um traceback feio:
    # mostra uma mensagem clara e finaliza com seguranca no bloco finally.
    try:
        menu()

        # TODO(AUTENTICACAO/PERMISSOES): apos validar login no servidor,
        # decidir aqui se o usuario tem perfil "administrador" antes de
        # chamar menu_admin(). Hoje a chamada foi removida do fluxo principal
        # porque nao deve ser oferecida a qualquer usuario sem checagem.
    except (ConnectionError, BrokenPipeError, OSError) as exc:
        tf.registrar_erro("cliente", exc, "canal perdido durante o menu")
        print("\n[CLIENTE] Conexao com o servidor perdida. Encerrando com seguranca.")
    except KeyboardInterrupt:
        print("\n[CLIENTE] Encerrado pelo usuario.")
    finally:
        conectado.clear()
        try:
            if sock is not None:
                sock.close()
        except OSError:
            pass
        thread_recebe.join(timeout=1)


def try_connection() -> socket.socket:
    # TOLERANCIA A FALHAS: em vez de uma unica tentativa que mata o programa,
    # tentamos algumas vezes com feedback claro. Esgotadas as tentativas, o
    # cliente sai com uma mensagem amigavel (e o erro fica registrado no log).
    try:
        return tf.conectar_com_retentativa(server_address, port)
    except tf.ErroAplicacao as exc:
        print(f"\n[CLIENTE] {exc.mensagem_usuario}")
        sys.exit(1)


def listen():
    """
    Roda em thread separada. So fica bloqueada no recv() -- e tudo bem
    ela ficar bloqueada, porque essa e a UNICA coisa que ela faz. A thread
    principal (menu/input) continua livre para interagir com o usuario.
    """
    while conectado.is_set():
        try:
            data = sock.recv(4096)
            if not data:
                # servidor encerrou a conexao do lado dele
                fila_recebidas.put("[conexão encerrada pelo servidor]")
                conectado.clear()
                break

            packet = data.decode("utf-8", errors="replace").strip()
            # Em vez de decidir aqui o que fazer com o pacote (a thread de
            # rede nao deve imprimir na tela por conta propria, para nao
            # embaralhar com o input() do usuario), so empilhamos na fila.
            # Quem desenha na tela e a thread principal, no momento certo.
            fila_recebidas.put(packet)

        except OSError as exc:
            # Acontece quando o socket e fechado (ex.: pelo menu, ao sair) ou
            # quando o canal cai. TOLERANCIA A FALHAS: registra e avisa o
            # usuario via fila, sem derrubar o cliente com traceback.
            if conectado.is_set():
                tf.registrar_erro("cliente.listen", exc, "falha ao receber do servidor")
                fila_recebidas.put("[conexao perdida com o servidor]")
            conectado.clear()
            break


def mostrar_mensagens_pendentes():
    """Drena a fila e imprime tudo que o servidor mandou ate agora."""
    while not fila_recebidas.empty():
        msg = fila_recebidas.get()
        # TOLERANCIA A FALHAS: se o servidor devolveu uma resposta de erro do
        # protocolo (ERRO|CODIGO|msg), exibimos de forma amigavel ao usuario.
        if tf.e_resposta_de_erro(msg):
            print(f"\n[ERRO DO SERVIDOR] {tf.descrever_erro_para_usuario(msg)}")
        else:
            print(f"\n[SERVIDOR] {msg}")


def menu():
    while conectado.is_set():
        mostrar_mensagens_pendentes()

        print("\n\nEscolha a opcao:\n")
        print("[1] fazer um pedido\n")
        print("[2] depositar creditos\n")
        print("[3] historico de pedidos\n")
        print("[4] processamento lento\n")
        print("[0] sair\n")

        op = input()
        match op:
            case "1":
                pedido()

            case "2":
                deposito()

            case "3":
                historico()
            case "4":
                menu_processamento_lento()
            case "0":
                sock.sendall(b"CLOSECONNECTION")
                conectado.clear()
                sock.close()
                break

            case _:
                print("opcao invalida")


def pedido():
    carrinho = []
    while True:
        for indice, item in enumerate(catalogo):
            print("[", indice, "] ", item.nome, "    R$", item.valor)
        print(
            "\nSelecione o item para adicionar ao carrinho, digite [voltar] "
            "para cancelar e [finalizar] para prosseguir com o pagamento\n"
        )
        op = input()

        if op == "finalizar":
            pagamento(carrinho)
            break

        if op == "voltar":
            break

        carrinho.append(op)


def pagamento(carrinho):
    # TODO(PROCESSAMENTO LENTO/MULTIPROCESSING) e TODO(SEGURANCA): o
    # protocolo real de envio (texto puro vs. criptografado, formato exato
    # da mensagem "LISTADEITENS") e definido pelos setores BASE/SEGURANCA.
    # Este setor so garante que o sendall() abaixo NAO trava o resto do
    # cliente, ja que quem escuta a resposta e a thread_recebe, nao o
    # menu().
    sock.sendall(b"LISTADEITENS")

    for indice_str in carrinho:
        if indice_str.isdigit() and int(indice_str) < len(catalogo):
            item = catalogo[int(indice_str)]
            sock.sendall(item.nome.encode("utf-8"))


def deposito():
    # TODO(AUTENTICACAO/PERMISSOES) e TODO(SEGURANCA): este setor so
    # garante a estrutura de envio/recebimento nao bloqueante. A regra de
    # negocio (valor minimo, validacao, criptografia do valor enviado)
    # fica a cargo dos setores responsaveis.
    print("\nDigite o valor a depositar:")
    valor = input()
    sock.sendall(f"DEPOSITO|{valor}".encode("utf-8"))


def historico():
    # TODO(LOGS): o historico de pedidos depende do sistema de logs/
    # persistencia em memoria definido pelo setor de LOGS, TESTES E
    # DOCUMENTACAO, e de permissoes do setor de AUTENTICACAO.
    sock.sendall(b"HISTORICO")


def menu_admin():
    # TODO(AUTENTICACAO/PERMISSOES): definir aqui as opcoes exclusivas do
    # perfil administrador. So deve ser chamada depois de confirmado que
    # o usuario logado tem permissao "administrador".
    pass

def menu_processamento_lento():
    print("\n=== PROCESSAMENTO LENTO ===")
    print("1. Simular Rota de Entrega (Permissão: Usuário Comum)")
    print("2. Rodar Auditoria de Vendas (Permissão: Administrador - Multiprocessing)")
    print("3. Voltar")
    
    opcao = input("Escolha uma opção de cálculo: ").strip()
    
    if opcao == "1":
        pedidos = input("Digite a quantidade de pedidos para simular (ex: 5): ").strip()
        # Envia no formato esperado pelo nosso gancho no servidor
        sock.sendall(f"CALCULO:SIMULAR_ENTREGA|{pedidos}".encode("utf-8"))
        print("Solicitação enviada. Aguardando resposta do servidor...")
        
    elif opcao == "2":
        registros = input("Digite o número de registros para a auditoria pesada (ex: 10000000): ").strip()
        # para o mock do servidor entender que somos admin."
        como_admin = input("Deseja simular como Administrador? (S/N): ").strip().upper()
        
        if como_admin == "S":
            sock.sendall(f"admin CALCULO:AUDITORIA_VENDAS|{registros}".encode("utf-8"))
        else:
            sock.sendall(f"CALCULO:AUDITORIA_VENDAS|{registros}".encode("utf-8"))
            
        print("Solicitação pesada enviada! Graças ao Multiprocessing, o servidor não vai travar.")
        
    elif opcao == "3":
        return
    else:
        print("Opção inválida.")


if __name__ == "__main__":
    main()