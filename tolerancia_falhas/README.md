# Setor 4 — TOLERÂNCIA A FALHAS

**Equipe:** José, Nicola e Guilherme

Este setor é responsável por **tratar o maior número possível de falhas** para que o
produto continue íntegro para o usuário, dando **feedback claro** quando algo dá errado e
**garantindo que o programa não encerre** diante de um erro de processo ou de canal.

> O setor **não** implementa regra de negócio de nenhum outro grupo. Ele oferece uma
> camada de **resiliência reutilizável** (`tolerancia_falhas/tolerancia_falhas.py`) e faz
> integrações **mínimas e cirúrgicas** no `server.py` e no `client.py`, exatamente nos
> pontos onde as falhas acontecem.

---

## 1. O que foi entregue (mapa das funções principais do setor)

| Função principal exigida no PDF | Onde está |
|---|---|
| Tratar os erros do lado do **servidor** | `server.py` → `atender_cliente` usa `processar_requisicao_segura` + `except` ampliado (timeout / canal / erro inesperado) |
| Tratar os erros do lado do **cliente** | `client.py` → `try_connection`, `listen` e o `menu()` protegido por `try/except/finally` em `main()` |
| **Feedback adequado** ao usuário | Protocolo padronizado `ERRO|CÓDIGO|mensagem` + exibição amigável no cliente (`descrever_erro_para_usuario`) |
| **Impedir que o programa encerre** diante de erro de processo/canal | Rede de segurança no servidor (a thread do cliente nunca morre por exceção não tratada) e `try/except/finally` no cliente |
| Tratar **conexão**, **mensagem inválida**, **timeout**, **sem permissão** e **API externa indisponível** | `traduzir_excecao`, `validar_mensagem`, timeout de inatividade, detecção de erro de permissão e `chamar_api_externa` |
| **Registrar erros nos logs** | Logger próprio `tolerancia_falhas` (arquivo + stderr); `registrar_erro` / `registrar_evento` |

### Entregas do setor
- ✅ Tratamento de exceções no **cliente**
- ✅ Tratamento de exceções no **servidor**
- ✅ Mensagens de erro **claras** para o usuário
- ✅ **Testes** demonstrando que o sistema continua funcionando após falhas (`test/teste_tolerancia_falhas.py`)

---

## 2. Protocolo de erro

Toda falha tratada é devolvida ao cliente no formato:

```
ERRO|<CÓDIGO>|<mensagem legível para o usuário>
```

Códigos previstos:

| Código | Quando acontece |
|---|---|
| `ERRO_CONEXAO` | canal indisponível / conexão recusada ou perdida |
| `ERRO_TIMEOUT` | servidor demorou demais / cliente inativo |
| `ERRO_REQUISICAO_INVALIDA` | mensagem mal formada (ex.: parâmetro não numérico) ou grande demais |
| `ERRO_PERMISSAO` | usuário sem permissão para a operação |
| `ERRO_API_EXTERNA` | serviço externo (API aberta) indisponível |
| `ERRO_INTERNO` | qualquer erro inesperado, tratado com segurança |

O cliente detecta a resposta de erro com `tf.e_resposta_de_erro(...)` e a exibe de forma
amigável, em vez de mostrar um traceback.

> Observação de integração: o setor de *Processamento Lento* já devolvia o texto
> `ERRO_AUTORIZACAO: ...` para o comando `CALCULO`. Mantivemos essa mensagem como está
> (para não alterar o código de outro setor); ela continua sendo um feedback claro de
> permissão. As demais falhas seguem o protocolo `ERRO|CÓDIGO|msg`.

---

## 3. Como usar o módulo (`import tolerancia_falhas as tf`)

```python
from tolerancia_falhas import tolerancia_falhas as tf

# --- SERVIDOR: rede de segurança em volta de qualquer despacho ---
resposta = tf.processar_requisicao_segura(
    processar_requisicao, texto, conn, endereco, origem=f"server[{endereco}]"
)  # nunca levanta exceção; sempre devolve uma string pronta para enviar

# --- CLIENTE: conectar com várias tentativas e feedback ---
sock = tf.conectar_com_retentativa("127.0.0.1", 40000)   # levanta ErroAplicacao se falhar

# --- APIs EXTERNAS: chamada resiliente (para o setor de APIs usar) ---
dados = tf.chamar_api_externa(
    minha_chamada_http, "https://viacep.com.br/ws/01001000/json/",
    tentativas=3, intervalo=0.5,
    fallback={"erro": "cep indisponível"},  # opcional: degrada sem quebrar
    nome_api="viacep",
)

# --- LOG de erros ---
tf.registrar_erro("meu_modulo", excecao, "contexto opcional")
```

Funções principais expostas: `formatar_erro`, `e_resposta_de_erro`,
`descrever_erro_para_usuario`, `traduzir_excecao`, `validar_mensagem`,
`processar_requisicao_segura`, `enviar_seguro`, `receber_seguro`,
`conectar_com_retentativa`, `chamar_api_externa`, `registrar_erro`, `registrar_evento`.

---

## 4. Configuração por variáveis de ambiente

| Variável | Padrão | Efeito |
|---|---|---|
| `TF_TIMEOUT_INATIVIDADE` | `300` | Segundos de inatividade até derrubar uma conexão pendurada. `0`/`none` desliga. |
| `TF_LOG_FILE` | `tolerancia_falhas/logs/tolerancia_falhas.log` | Caminho do arquivo de log de erros. |

---

## 5. Como testar

Na **raiz do projeto**:

```bash
# Todos os testes do setor
python3 -m unittest test/teste_tolerancia_falhas.py -v

# Ou direto:
python3 test/teste_tolerancia_falhas.py
```

- **Testes de unidade** do módulo rodam em qualquer Python ≥ 3.9.
- **Testes de integração** sobem o servidor de verdade (subprocess) e provam que ele
  **continua atendendo novos clientes** depois de uma sequência de falhas (mensagem
  inválida → sem permissão → cliente que cai → comando normal volta a funcionar). Também
  há um teste do **timeout de inatividade**.

### Demonstração manual rápida

```bash
# Terminal 1
python3 server.py

# Terminal 2 — provoca um erro e vê o servidor seguir vivo
python3 - <<'PY'
import socket
def troca(msg):
    s = socket.socket(); s.connect(("127.0.0.1", 40000))
    s.sendall(msg.encode()); print(s.recv(4096).decode()); s.close()
troca("CALCULO:SIMULAR_ENTREGA|abc")   # ERRO|ERRO_REQUISICAO_INVALIDA|...
troca("LISTADEITENS")                  # servidor continua respondendo normalmente
PY
```

Para ver o **timeout** em ação, suba o servidor com um valor baixo e conecte sem enviar nada:

```bash
TF_TIMEOUT_INATIVIDADE=3 python3 server.py
```

---

## 6. Checklist de falhas tratadas

- [x] Conexão recusada / servidor fora do ar (cliente tenta de novo e avisa)
- [x] Conexão perdida no meio da sessão (cliente e servidor seguem sem traceback)
- [x] Mensagem mal formada / parâmetro inválido (erro padronizado, sem derrubar a thread)
- [x] Mensagem grande demais (validação `validar_mensagem`)
- [x] Timeout de inatividade (servidor libera a thread e dá feedback)
- [x] Usuário sem permissão (feedback claro)
- [x] API externa indisponível (retentativa + fallback, ferramenta para o setor de APIs)
- [x] Erro inesperado qualquer (última barreira: tratado, logado e o servidor segue vivo)
- [x] Todos os erros acima são **registrados em log**
