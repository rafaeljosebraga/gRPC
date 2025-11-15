# Chat gRPC - Guia de Instalação e Uso

## 1. Instalação de Dependências

Instale as bibliotecas necessárias do gRPC:

```bash
python -m pip install grpcio grpcio-tools
```

## 2. Gerar Stubs (executar apenas uma vez)

Compile o arquivo `.proto` para gerar os arquivos Python necessários:

```bash
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chat.proto
```

## 3. Executar a Aplicação

### Terminal 1 - Servidor

Inicie o servidor gRPC:

```bash
python server_grpc.py
```

### Terminal 2 - Cliente

Conecte-se ao servidor:

```bash
# Conexão local (padrão)
python client_grpc.py
```

O cliente conecta em `localhost:50051` por padrão.

## 4. Como Usar o Cliente

### Login/Cadastro Automático

Ao iniciar, o cliente solicitará:

- **Usuário:** `<nome>`
- **Senha:** `<senha>`

Se a conta não existir, será criada automaticamente. Caso contrário, você fará login.

### Enviar Mensagens

Digite suas mensagens normalmente e pressione Enter para enviá-las.

### Comandos Disponíveis

| Comando | Descrição |
|---------|-----------|
| `/hist` | Exibe as últimas no histórico |
| `/quit` | Sair do chat |

## Exemplo de Uso

```
Usuário: joao
Senha: ****
[Sistema] Conta criada com sucesso!

joao: Olá, pessoal!
maria: Oi, João! Tudo bem?
joao: /hist
[Sistema] Últimas 20 mensagens:
  [2025-11-14 10:30] joao: Olá, pessoal!
  [2025-11-14 10:31] maria: Oi, João! Tudo bem?

joao: /quit
[Sistema] Desconectando...
```
