import socket
import threading

HOST_IP = socket.gethostbyname(socket.gethostname())
HOST_PORT = 12345
ENCODER = "utf-8"
BYTESIZE = 1024

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST_IP, HOST_PORT))
server_socket.listen()

stop = False

client_socket_list = []
client_name_list = []


def broadcast_message(message, source_socket=None):
    for client in client_socket_list:
        if client != source_socket:
            try:
                client.send(message.encode(ENCODER))
            except:
                client_socket_list.remove(client)
    pass


def receive_message(client_socket):
    global stop

    while not stop:
        try:
            message = client_socket.recv(BYTESIZE).decode(ENCODER)

            if not message:
                break  # Cliente desconectou
            
            # Comando para parar o servidor
            if message == "/stopServer":
                broadcast_message("O servidor foi desligado pelo administrador.")
                print("\nEncerrando o servidor...")
                stop = True
                break
            
            # Envia mensagem aos outros clientes
            broadcast_message(message, source_socket=client_socket)

        except ConnectionResetError:
            break
    
    # Remover cliente ao sair
    if client_socket in client_socket_list:
        client_socket_list.remove(client_socket)
    client_socket.close()


def connect_client():
    """
    Aceita novos clientes e cria UMA THREAD por cliente
    para rodar receive_message().
    """
    global stop

    print(f"Servidor iniciado em {HOST_IP}:{HOST_PORT}")

    while not stop:
        try:
            client_socket, client_address = server_socket.accept()

            client_socket_list.append(client_socket)
            client_name_list.append(client_address)

            print(f"Conectado a {client_address}!")

            client_socket.send("Você está conectado ao servidor!".encode(ENCODER))

            message_thread = threading.Thread(
                target=receive_message,
                args=(client_socket,),
                daemon=True
            )
            message_thread.start()

        except OSError:
            break  # O socket foi fechado quando stop == True


# THREAD principal de conexão
connectionThread = threading.Thread(target=connect_client, daemon=True)
connectionThread.start()

# Mantém o servidor ativo
try:
    while not stop:
        pass
except KeyboardInterrupt:
    pass

# Encerrar
server_socket.close()
print("Servidor encerrado.")
