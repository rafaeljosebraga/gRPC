import socket
import threading

DEST_IP = socket.gethostbyname(socket.gethostname())
DEST_PORT = 12345
ENCODER = "utf-8"
BYTESIZE = 1024

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((DEST_IP, DEST_PORT))

stop = False


def send_message():
    global stop

    while not stop:
        try:
            message = input()

            if message == "/quit":
                client_socket.close()
                stop = True
                break

            client_socket.send(message.encode(ENCODER))

        except (BrokenPipeError, OSError):
            break


def receive_message():
    global stop

    while not stop:
        try:
            message = client_socket.recv(BYTESIZE).decode(ENCODER)

            if not message:
                print("\nServidor desconectou.")
                stop = True
                break

            print(message)

        except (ConnectionResetError, OSError):
            break


# THREADS DO CLIENTE
sendThread = threading.Thread(target=send_message, daemon=True)
receiveThread = threading.Thread(target=receive_message, daemon=True)

sendThread.start()
receiveThread.start()

# Mantém cliente vivo até ambas as threads encerrarem
sendThread.join()
receiveThread.join()

