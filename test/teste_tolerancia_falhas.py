"""
=============================================================================
SETOR: TOLERANCIA A FALHAS  (Jose, Nicola e Guilherme)
Testes demonstrando que o sistema TRATA falhas e CONTINUA FUNCIONANDO.
=============================================================================

Duas frentes:

  1) TesteModuloToleranciaFalhas
     Testes de unidade do modulo de tolerancia a falhas (sem rede). Rodam em
     qualquer versao de Python (>= 3.9).

  2) TesteServidorResiliencia / TesteTimeoutInatividade
     Testes de INTEGRACAO: sobem o servidor de verdade (subprocess), provocam
     varias falhas (mensagem invalida, sem permissao, cliente que cai, timeout)
     e provam que o servidor CONTINUA atendendo novos clientes.
     Exigem Python 3.10+ (o server.py usa match/case) e a porta 40000 livre.

Como rodar (na raiz do projeto):
    python3 -m unittest test/teste_tolerancia_falhas.py -v
ou simplesmente:
    python3 test/teste_tolerancia_falhas.py
=============================================================================
"""

import os
import sys
import time
import socket
import subprocess
import unittest

# Garante que a raiz do projeto esteja no path para importar os modulos.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from tolerancia_falhas import tolerancia_falhas as tf

# server.py usa match/case (3.10+). Em Python mais antigo, importar levanta
# SyntaxError -- que capturamos para pular os testes que dependem dele.
try:
    import server  # noqa: E402

    SERVER_DISPONIVEL = True
except SyntaxError:
    SERVER_DISPONIVEL = False


HOST = "127.0.0.1"
PORTA = 40000


# ---------------------------------------------------------------------------
# Auxiliares de rede para os testes de integracao.
# ---------------------------------------------------------------------------
def _porta_ocupada(host, porta):
    """True se ja existe alguem escutando na porta (servidor ja rodando)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect((host, porta))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _esperar_servidor(host, porta, timeout=8.0):
    """Espera o servidor comecar a aceitar conexoes; True se subiu a tempo."""
    limite = time.time() + timeout
    while time.time() < limite:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect((host, porta))
            s.close()
            return True
        except OSError:
            time.sleep(0.15)
        finally:
            try:
                s.close()
            except OSError:
                pass
    return False


def _enviar_e_receber(mensagem, host=HOST, porta=PORTA, timeout=8.0):
    """Conecta, envia uma mensagem, le UMA resposta e fecha. Devolve string."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, porta))
        s.sendall(mensagem.encode("utf-8"))
        dados = s.recv(4096)
        return dados.decode("utf-8", errors="replace")
    finally:
        try:
            s.close()
        except OSError:
            pass


def _conectar_e_cair(host=HOST, porta=PORTA):
    """Simula um cliente que conecta e cai abruptamente (sem CLOSECONNECTION)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    s.connect((host, porta))
    # fecha sem avisar -> queda abrupta do canal do ponto de vista do servidor
    s.close()


# ===========================================================================
# 1) TESTES DE UNIDADE DO MODULO (sem rede)
# ===========================================================================
class TesteModuloToleranciaFalhas(unittest.TestCase):

    # ---- protocolo de erro ----
    def test_formatar_e_detectar_erro(self):
        resposta = tf.formatar_erro(tf.ERRO_PERMISSAO, "sem acesso")
        self.assertTrue(resposta.startswith("ERRO|ERRO_PERMISSAO|"))
        self.assertTrue(resposta.endswith("\n"))
        self.assertTrue(tf.e_resposta_de_erro(resposta))
        self.assertFalse(tf.e_resposta_de_erro("ITENS:\n0 - coxinha"))

    def test_formatar_erro_usa_mensagem_padrao(self):
        resposta = tf.formatar_erro(tf.ERRO_TIMEOUT)
        self.assertIn(tf.MENSAGENS_PADRAO[tf.ERRO_TIMEOUT].replace("\n", " "), resposta)

    def test_descrever_erro_para_usuario(self):
        amigavel = tf.descrever_erro_para_usuario("ERRO|ERRO_CONEXAO|canal caiu")
        self.assertIn("canal caiu", amigavel)
        self.assertIn("ERRO_CONEXAO", amigavel)
        # texto que nao e erro volta como veio
        self.assertEqual(tf.descrever_erro_para_usuario("ola"), "ola")

    # ---- traducao de excecoes ----
    def test_traduzir_excecao_conhecidas(self):
        self.assertEqual(tf.traduzir_excecao(ValueError("x"))[0], tf.ERRO_REQUISICAO_INVALIDA)
        self.assertEqual(tf.traduzir_excecao(IndexError())[0], tf.ERRO_REQUISICAO_INVALIDA)
        self.assertEqual(tf.traduzir_excecao(ConnectionResetError())[0], tf.ERRO_CONEXAO)
        self.assertEqual(tf.traduzir_excecao(socket.timeout())[0], tf.ERRO_TIMEOUT)
        self.assertEqual(tf.traduzir_excecao(RuntimeError("?"))[0], tf.ERRO_INTERNO)

    def test_traduzir_erro_de_permissao_de_outro_setor(self):
        # Simula a excecao do setor de Processamento Lento, SEM importa-la,
        # para provar que reconhecemos pelo nome da classe.
        class PermissaoNegadaError(Exception):
            pass

        codigo, _ = tf.traduzir_excecao(PermissaoNegadaError("sem permissao"))
        self.assertEqual(codigo, tf.ERRO_PERMISSAO)

    def test_erro_aplicacao_preserva_codigo(self):
        exc = tf.PermissaoError("nao pode")
        self.assertEqual(tf.traduzir_excecao(exc), (tf.ERRO_PERMISSAO, "nao pode"))

    # ---- validacao de mensagem ----
    def test_validar_mensagem(self):
        self.assertEqual(tf.validar_mensagem("ola"), "ola")
        self.assertEqual(tf.validar_mensagem(""), "")  # vazio e permitido
        with self.assertRaises(tf.RequisicaoInvalidaError):
            tf.validar_mensagem("x" * (tf.TAMANHO_MAXIMO_MENSAGEM + 1))
        with self.assertRaises(tf.RequisicaoInvalidaError):
            tf.validar_mensagem(None)

    # ---- rede de seguranca do servidor ----
    def test_processar_requisicao_segura_captura_excecao(self):
        def funcao_que_explode(_):
            raise ValueError("boom")

        resposta = tf.processar_requisicao_segura(funcao_que_explode, "qualquer")
        self.assertTrue(tf.e_resposta_de_erro(resposta))
        self.assertIn(tf.ERRO_REQUISICAO_INVALIDA, resposta)

    def test_processar_requisicao_segura_repassa_sucesso(self):
        resposta = tf.processar_requisicao_segura(lambda t: "OK:" + t, "abc")
        self.assertEqual(resposta, "OK:abc")

    # ---- conexao com retentativa (porta fechada) ----
    def test_conectar_com_retentativa_falha_controlada(self):
        with self.assertRaises(tf.ErroAplicacao) as ctx:
            # porta com altissima chance de estar fechada
            tf.conectar_com_retentativa(
                "127.0.0.1", 59999, tentativas=2, intervalo=0.01, timeout_conexao=0.5
            )
        self.assertEqual(ctx.exception.codigo, tf.ERRO_CONEXAO)

    # ---- chamada resiliente a API externa ----
    def test_api_externa_sucesso_apos_falhas(self):
        estado = {"chamadas": 0}

        def chamada_instavel():
            estado["chamadas"] += 1
            if estado["chamadas"] < 3:
                raise ConnectionError("instavel")
            return {"ok": True}

        resultado = tf.chamar_api_externa(chamada_instavel, tentativas=3, intervalo=0.01)
        self.assertEqual(resultado, {"ok": True})
        self.assertEqual(estado["chamadas"], 3)

    def test_api_externa_usa_fallback(self):
        def sempre_falha():
            raise TimeoutError("api fora do ar")

        resultado = tf.chamar_api_externa(
            sempre_falha, tentativas=2, intervalo=0.01, fallback={"cache": "antigo"}
        )
        self.assertEqual(resultado, {"cache": "antigo"})

    def test_api_externa_sem_fallback_levanta(self):
        def sempre_falha():
            raise ConnectionError("api fora do ar")

        with self.assertRaises(tf.ErroAPIExterna):
            tf.chamar_api_externa(sempre_falha, tentativas=2, intervalo=0.01)


# ===========================================================================
# 1b) TESTES DA REDE DE SEGURANCA APLICADA AO DESPACHADOR REAL DO SERVIDOR
#     (sem rede; so chama processar_requisicao com a rede de seguranca)
# ===========================================================================
@unittest.skipUnless(SERVER_DISPONIVEL, "server.py exige Python 3.10+ (match/case)")
class TesteDespachoServidorSeguro(unittest.TestCase):

    def _seguro(self, texto):
        return tf.processar_requisicao_segura(
            server.processar_requisicao, texto, None, None, origem="teste"
        )

    def test_calculo_com_parametro_invalido_nao_levanta(self):
        # int("abc") explodiria; a rede de seguranca transforma em erro limpo.
        resposta = self._seguro("CALCULO:SIMULAR_ENTREGA|abc")
        self.assertTrue(tf.e_resposta_de_erro(resposta))
        self.assertIn(tf.ERRO_REQUISICAO_INVALIDA, resposta)

    def test_sem_permissao_devolve_mensagem_limpa(self):
        # AUDITORIA_VENDAS exige admin; usuario comum recebe mensagem clara.
        resposta = self._seguro("CALCULO:AUDITORIA_VENDAS|10")
        self.assertNotEqual(resposta, "")
        self.assertTrue(
            "permiss" in resposta.lower() or "ERRO" in resposta.upper(),
            msg=f"esperava feedback de permissao, veio: {resposta!r}",
        )

    def test_comando_normal_continua_funcionando(self):
        resposta = self._seguro("LISTADEITENS")
        self.assertTrue(resposta.startswith("ITENS:"))


# ===========================================================================
# 2) TESTE DE INTEGRACAO: servidor resiste a uma sequencia de falhas
# ===========================================================================
@unittest.skipUnless(SERVER_DISPONIVEL, "server.py exige Python 3.10+ (match/case)")
class TesteServidorResiliencia(unittest.TestCase):
    proc = None

    @classmethod
    def setUpClass(cls):
        if _porta_ocupada(HOST, PORTA):
            raise unittest.SkipTest(
                f"porta {PORTA} ja esta ocupada (servidor rodando?); pulei o teste de integracao"
            )
        env = dict(os.environ)
        env["TF_TIMEOUT_INATIVIDADE"] = "0"  # sem timeout idle aqui
        cls.proc = subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=RAIZ,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _esperar_servidor(HOST, PORTA, timeout=8.0):
            cls.proc.terminate()
            raise unittest.SkipTest("servidor nao subiu a tempo")

    @classmethod
    def tearDownClass(cls):
        if cls.proc is not None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()

    def test_servidor_resiste_a_sequencia_de_falhas(self):
        # 1) Mensagem mal formada (parametro nao numerico) -> antes derrubaria
        #    a thread com ValueError; agora vira erro padronizado e tratado.
        r1 = _enviar_e_receber("CALCULO:SIMULAR_ENTREGA|abc")
        self.assertTrue(
            tf.e_resposta_de_erro(r1),
            msg=f"esperava resposta de erro padronizada, veio: {r1!r}",
        )
        self.assertIn(tf.ERRO_REQUISICAO_INVALIDA, r1)

        # 2) Operacao sem permissao -> feedback claro, sem derrubar a conexao.
        r2 = _enviar_e_receber("CALCULO:AUDITORIA_VENDAS|10")
        self.assertTrue(
            "permiss" in r2.lower() or "ERRO" in r2.upper(),
            msg=f"esperava feedback de permissao, veio: {r2!r}",
        )

        # 3) Cliente que conecta e cai abruptamente (sem CLOSECONNECTION).
        _conectar_e_cair()

        # 4) PROVA FINAL: depois de TODAS as falhas acima, o servidor ainda
        #    atende um cliente novo normalmente.
        r_final = _enviar_e_receber("LISTADEITENS")
        self.assertTrue(
            r_final.startswith("ITENS:"),
            msg=f"servidor deveria continuar vivo e responder ITENS, veio: {r_final!r}",
        )


# ===========================================================================
# 2b) TESTE DE INTEGRACAO: timeout de inatividade encerra com feedback,
#     mas o servidor continua atendendo novos clientes.
# ===========================================================================
@unittest.skipUnless(SERVER_DISPONIVEL, "server.py exige Python 3.10+ (match/case)")
class TesteTimeoutInatividade(unittest.TestCase):
    proc = None

    @classmethod
    def setUpClass(cls):
        if _porta_ocupada(HOST, PORTA):
            raise unittest.SkipTest(f"porta {PORTA} ocupada; pulei o teste de timeout")
        env = dict(os.environ)
        env["TF_TIMEOUT_INATIVIDADE"] = "2"  # 2s de inatividade derruba a conexao
        cls.proc = subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=RAIZ,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _esperar_servidor(HOST, PORTA, timeout=8.0):
            cls.proc.terminate()
            raise unittest.SkipTest("servidor nao subiu a tempo")

    @classmethod
    def tearDownClass(cls):
        if cls.proc is not None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()

    def test_timeout_de_inatividade_da_feedback(self):
        # Conecta e fica em silencio. O servidor deve mandar um erro de
        # timeout (~2s) e encerrar a conexao -- sem travar a thread.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(8.0)
        try:
            s.connect((HOST, PORTA))
            dados = s.recv(4096).decode("utf-8", errors="replace")
        finally:
            s.close()
        self.assertIn(tf.ERRO_TIMEOUT, dados)

        # E o servidor continua vivo para um novo cliente.
        r = _enviar_e_receber("LISTADEITENS")
        self.assertTrue(r.startswith("ITENS:"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
