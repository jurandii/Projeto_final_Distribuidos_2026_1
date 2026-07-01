======================================================================================================================================

PARTICIPANTES JOÃO TONELLO & BRENO.

# Módulo de Segurança

## Descrição

Este módulo foi desenvolvido para implementar uma camada de segurança na comunicação entre o cliente e o servidor do projeto de Sistemas Distribuídos.

Seu objetivo é proteger os dados trafegados na rede, validar mensagens recebidas e reduzir riscos relacionados à entrada de dados inválidos.

## Funcionalidades

* Criptografia e descriptografia de mensagens utilizando a biblioteca **cryptography (Fernet)**.
* Geração de chave criptográfica.
* Validação do tamanho das mensagens.
* Validação de mensagens em formato JSON.
* Validação de comandos permitidos.
* Sanitização básica das entradas recebidas.

## Estrutura

```text
seguranca/
│── __init__.py
│── criptografia.py
│── gerar_chave.py
│── validacao.py
│── chave.key #Gerado Automaticamente!
│── README.md
```

## Dependências

Instale a biblioteca necessária:

```bash
pip install cryptography
```

## Geração da chave

Antes de executar o sistema, gere a chave criptográfica:

```bash
python gerar_chave.py
```

O comando criará automaticamente o arquivo:

```text
chave.key
```

Este arquivo será utilizado pelo cliente e pelo servidor para criptografar e descriptografar as mensagens.

## Utilização

### Criptografar uma mensagem

```python
from seguranca.criptografia import criptografar

mensagem = criptografar("Olá servidor!")
```

### Descriptografar uma mensagem

```python
from seguranca.criptografia import descriptografar

texto = descriptografar(mensagem)
```

## Validação

O módulo `validacao.py` possui funções para:

* verificar tamanho máximo das mensagens;
* validar mensagens JSON;
* validar comandos permitidos;
* realizar uma sanitização básica das entradas.

Essas verificações ajudam a evitar processamento de mensagens inválidas e aumentam a segurança da aplicação.

## Observações

Este módulo foi desenvolvido para ser integrado ao `client.py` e ao `server.py`, permitindo que todas as mensagens trocadas entre cliente e servidor sejam protegidas por criptografia.

A integração completa dependerá da arquitetura adotada pelos demais módulos do projeto.

## Autor

Desenvolvido para o setor de **Segurança** do Projeto Final da disciplina de Sistemas Distribuídos.


======================================================================================================================================
