# Projeto_final_Distribuidos_2026_1
Projeto focado na entrega do trabalho final da atividade de sistemas distribuidos do primeiro período de 2026

# Setor BASE

Aplicativo para pedidos e entrega de lanches.

# Setor THREADS

Garantir que o servidor atenda múltiplos clientes ao mesmo tempo e que o cliente não trave esperando resposta do servidor.

# Setor TOLERÂNCIA A FALHAS

Tratar o maior número possível de falhas (conexão, mensagem inválida, timeout, sem permissão, API externa indisponível e erros inesperados), dar feedback claro ao usuário e impedir que cliente ou servidor encerrem por um erro. Detalhes, uso e testes em [`tolerancia_falhas/README.md`](tolerancia_falhas/README.md).


# Sobre o Projeto


## Arquivos

- `server.py` — servidor TCP. Cria uma thread nova para cada cliente que conecta.
- `client.py` — cliente TCP. Usa uma thread separada para escutar o servidor enquanto o menu (input do usuário) roda na thread principal.

## Como rodar

Em um terminal, inicie o servidor:

```bash
python3 server.py
```

Em outro terminal, rode o cliente:

```bash
python3 client.py
```

## Requisitos

- Python 3.10+ (usa `match/case`)
- Nenhuma biblioteca externa — só módulos padrão (`socket`, `threading`, `queue`)
