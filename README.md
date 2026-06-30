# Projeto Final — Sistemas Distribuídos

Sistema distribuído em Python, composto por cliente e servidor, simulando uma plataforma de pedidos e entrega de lanches. Desenvolvido como trabalho final da disciplina de Sistemas Distribuídos (2026/1), com responsabilidades divididas entre 23 alunos organizados em 8 setores: comunicação em rede, concorrência, segurança, tolerância a falhas, autenticação, processamento pesado, integração externa e documentação.

---

## Sobre o Projeto

O produto final é uma aplicação distribuída composta por um cliente e um servidor Python, executados separadamente e comunicando-se por sockets TCP. O cliente permite que o usuário faça login, monte pedidos, deposite créditos, consulte histórico e solicite processamentos ao servidor. O servidor autentica usuários, valida permissões, executa os comandos recebidos, despacha cálculos lentos e registra logs das operações.

Conceitos de sistemas distribuídos demonstrados: comunicação cliente-servidor, chamadas remotas, concorrência com threads, processamento paralelo com multiprocessing, tolerância a falhas, controle de permissões e, em desenvolvimento, criptografia e integração com APIs externas.

Observação: não há banco de dados. Usuários e dados de exemplo são mantidos em memória/código, conforme regra explícita do projeto.

---

## Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/jurandii/Projeto_final_Distribuidos_2026_1.git
cd Projeto_final_Distribuidos_2026_1
```

### 2. Requisitos

- Python 3.10 ou superior;
- Nenhuma dependência externa obrigatória — apenas módulos padrão da linguagem (`socket`, `threading`, `queue`, `json`, `hashlib`, `concurrent.futures`, `logging`)

---

## Como Rodar

Em um terminal, inicie o servidor:

```bash
python3 server.py
```

Em outro terminal, execute o cliente:

```bash
python3 client.py
```

O servidor escuta em `127.0.0.1:40000`.

---

## Protocolo de Comunicação

A comunicação ocorre via sockets TCP, com mensagens em texto (UTF-8). Comandos enviados do cliente para o servidor:

| Comando | Formato | Descrição |
|---|---|---|
| `LISTADEITENS` | `LISTADEITENS` | Lista o cardápio disponível |
| `DEPOSITO` | `DEPOSITO\|<valor>` | Deposita créditos na conta do usuário |
| `HISTORICO` | `HISTORICO` | Consulta o histórico de pedidos (depende do setor de Logs) |
| `CALCULO` | `CALCULO:<OPERACAO>\|<parametro>` | Solicita um processamento lento ao servidor. Exemplos: `CALCULO:SIMULAR_ENTREGA\|5`, `CALCULO:AUDITORIA_VENDAS\|20000000` |
| `CLOSECONNECTION` | `CLOSECONNECTION` | Encerra a sessão com o servidor |

Qualquer comando não reconhecido recebe uma resposta padrão de eco (`DEMO_TCP_OK`).

As respostas de erro seguem um formato padronizado:

```
ERRO|<CÓDIGO>|<mensagem legível para o usuário>
```

Códigos de erro previstos: `ERRO_CONEXAO`, `ERRO_TIMEOUT`, `ERRO_REQUISICAO_INVALIDA`, `ERRO_PERMISSAO`, `ERRO_API_EXTERNA`, `ERRO_INTERNO`.

Nota: a criptografia dos dados trafegados ainda está pendente de implementação pelo setor de Segurança.

---

## Estrutura

```
Projeto_final_Distribuidos_2026_1/
├── LICENSE
├── README.md
├── server.py                          # Servidor TCP — accept() em loop + thread por cliente
├── client.py                          # Cliente TCP — thread de escuta + menu interativo
├── autenticacao/
│   ├── README.md
│   └── autenticacao.py                # Login, usuários em JSON, hash SHA-256 de senha
├── processamento_lento/
│   ├── README.md
│   └── processamento_lento.py         # Cálculos lentos (básico/avançado) + multiprocessing
├── tolerancia_falhas/
│   ├── README.md
│   ├── tolerancia_falhas.py           # Rede de segurança, retentativas, protocolo de erro, logs
│   └── logs/                          # Criada automaticamente em tempo de execução (arquivo de log)
└── test/
    ├── EXPLICACAO_THREADS.md          # Explicação técnica do uso de threads
    ├── teste_concorrencia.py          # Simula múltiplos clientes simultâneos
    └── teste_tolerancia_falhas.py     # Testes de unidade e integração de falhas
```

---

## Setores e Equipes

| Setor | Alunos | Quantidade |
|---|---|---|
| Base | Iuri, Guilherme S, Nathan K | 4 |
| Threads | Roger, Jean e Lourenço | 3 |
| Segurança | Gabriel Victor, Breno e João Tonello | 3 |
| Tolerância a Falhas | Nicola, José e Guilherme | 3 |
| Autenticação, Usuários e Permissões | Peruzzo e Carlos | 2 |
| Processamento Lento e Multiprocessing | Ana, Alisson e Samayra | 3 |
| APIs Externas Abertas | Mateus de Sousa, Cristian Vital, Gabriel Fuck | 3 |
| Logs, Testes e Documentação | Lucas F. e Myguel | 2 |

---

## Stack Tecnológico

**Linguagem**
Python 3.10 ou superior, para cliente e servidor.

**Comunicação**
Sockets TCP, via módulo padrão `socket`.

**Concorrência**
`threading` — uma thread dedicada por cliente conectado no servidor; thread de escuta dedicada no cliente.

**Processamento paralelo**
`multiprocessing`, via `concurrent.futures.ProcessPoolExecutor`, para cálculos administrativos pesados, sem bloquear o servidor.

**Autenticação**
Usuários definidos em JSON em memória, com senha armazenada como hash SHA-256 (`hashlib`). Sem banco de dados.

**Logs**
Módulo padrão `logging`, com saída em arquivo e em tela.

---

## Concorrência (Threads)

A thread principal do servidor executa apenas `accept()` em loop. Cada conexão aceita recebe sua própria thread (`atender_cliente`), permitindo atender múltiplos clientes simultaneamente sem bloqueio.

No cliente, uma thread dedicada cuida exclusivamente do `recv()` e empilha as mensagens recebidas em uma `queue.Queue`. A thread principal cuida do menu e do `input()` do usuário, exibindo as mensagens pendentes antes de cada interação.

---

## Processamento Lento e Multiprocessing

| Operação | Permissão | Mecanismo |
|---|---|---|
| `SIMULAR_ENTREGA` | Usuário comum | Loop sequencial na thread do cliente |
| `AUDITORIA_VENDAS` | Administrador | `ProcessPoolExecutor` (processo separado do sistema operacional) |

Uma tentativa de executar `AUDITORIA_VENDAS` sem permissão de administrador retorna `ERRO_AUTORIZACAO`.

Pendência confirmada em teste: o cliente envia o prefixo `admin` antes de `CALCULO:`, mas o servidor só identifica o comando se a mensagem começar com `CALCULO:`. Na prática, o fluxo de admin do cliente nunca aciona a auditoria — precisa de ajuste de um dos dois lados.

---

## Segurança

A estrutura de login e permissões já está implementada em `autenticacao/autenticacao.py`:

```json
{
  "usuarios": [
    { "usuario": "admin", "perfil": "administrador", "permissoes": ["basico", "avancado"] },
    { "usuario": "aluno", "perfil": "usuario", "permissoes": ["basico"] }
  ]
}
```

As senhas são armazenadas exclusivamente como hash SHA-256, nunca em texto puro. A criptografia dos dados trafegados entre cliente e servidor, bem como a integração desse módulo ao fluxo principal de `server.py`, ainda estão pendentes.

---

## Tolerância a Falhas

Camada de resiliência reutilizável, implementada em `tolerancia_falhas/tolerancia_falhas.py` e utilizada por servidor e cliente para:

- evitar que exceções não tratadas encerrem a thread de atendimento de um cliente;
- padronizar o feedback de erro no formato `ERRO|CÓDIGO|mensagem`;
- tratar conexão recusada ou perdida, mensagem inválida, timeout de inatividade, permissão negada e indisponibilidade de API externa;
- registrar todos os erros em log.

---

## Como Testar

**Concorrência** — simula três clientes conectados simultaneamente, um deles com resposta lenta:

```bash
# terminal 1
python3 server.py
# terminal 2
python3 test/teste_concorrencia.py
```

**Tolerância a falhas** — testes de unidade e integração:

```bash
python3 -m unittest test/teste_tolerancia_falhas.py -v
```

---

## Licença

Uso acadêmico — Trabalho Final de Sistemas Distribuídos, UTFPR (2026/1).

## Agradecimentos 

Deus & Claude. 