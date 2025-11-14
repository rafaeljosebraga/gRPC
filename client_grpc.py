import grpc
import threading
import queue
import sys
import signal
import getpass
import chat_pb2
import chat_pb2_grpc

class ChatClient:
    def __init__(self, server_address="localhost:50051"):
        self.server_address = server_address
        self.send_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.username = None
        self.authenticated = False
        self.channel = None
        self.stub = None
        
    def request_generator(self):
        """Generator que envia mensagens do cliente para o servidor."""
        while not self.stop_event.is_set():
            try:
                message = self.send_queue.get(timeout=0.1)
                if message is None:  # sinal de encerramento
                    break
                yield chat_pb2.Message(username=self.username or "unknown", text=message)
            except queue.Empty:
                continue
    
    def send_messages(self):
        """Thread que lê input do usuário e envia para a fila."""
        # Aguardar autenticação
        while not self.authenticated and not self.stop_event.is_set():
            import time
            time.sleep(0.1)
        
        if self.stop_event.is_set():
            return
        
        print("\n[Chat iniciado! Digite suas mensagens. Use /help para ajuda]\n")
        
        while not self.stop_event.is_set():
            try:
                text = input()
                if self.stop_event.is_set():
                    break
                    
                if text.lower() == "/quit":
                    self.shutdown()
                    break
                    
                if text.strip():  # ignora mensagens vazias
                    self.send_queue.put(text)
                    
            except (EOFError, KeyboardInterrupt):
                self.shutdown()
                break
            except Exception as e:
                print(f"\n[Erro ao enviar mensagem: {e}]")
    
    def receive_messages(self, responses):
        """Thread que recebe mensagens do servidor."""
        try:
            for response in responses:
                if self.stop_event.is_set():
                    break
                
                # Mensagem do sistema ou de outros usuários
                if response.username == "Sistema":
                    print(f"\n[SISTEMA] {response.text}")
                    
                    # Detectar autenticação bem-sucedida
                    if "Bem-vindo," in response.text and not self.authenticated:
                        self.authenticated = True
                else:
                    # Não imprime a própria mensagem de volta
                    if response.username != self.username:
                        print(f"\n{response.username}: {response.text}")
                    
        except grpc.RpcError as e:
            if not self.stop_event.is_set():
                print(f"\n[Erro de conexão: {e.code()}]")
        finally:
            self.shutdown()
    
    def authenticate(self):
        """
        Processo de autenticação.
        Retorna True se bem-sucedido, False caso contrário.
        """
        print("\n=== AUTENTICAÇÃO ===")
        print("Primeira vez? Sua senha será registrada.")
        print("Já tem conta? Use suas credenciais.\n")
        
        try:
            username = input("Usuário: ").strip()
            if not username:
                print("[Erro: Nome de usuário não pode ser vazio]")
                return False
            
            # Usar getpass para ocultar senha (funciona em terminal)
            try:
                password = getpass.getpass("Senha: ").strip()
            except:
                # Fallback se getpass não funcionar
                password = input("Senha: ").strip()
            
            if not password:
                print("[Erro: Senha não pode ser vazia]")
                return False
            
            self.username = username
            
            # Enviar credenciais no formato USERNAME:PASSWORD
            credentials = f"{username}:{password}"
            self.send_queue.put(credentials)
            
            print("\n[Aguardando autenticação do servidor...]")
            
            # Aguardar confirmação (timeout de 10 segundos)
            timeout = 10
            start_time = import_time()
            
            while not self.authenticated and not self.stop_event.is_set():
                if import_time() - start_time > timeout:
                    print("[Erro: Timeout na autenticação]")
                    return False
                import_sleep(0.1)
            
            return self.authenticated
            
        except (EOFError, KeyboardInterrupt):
            print("\n[Autenticação cancelada]")
            return False
    
    def shutdown(self):
        """Encerra o cliente de forma graceful."""
        if not self.stop_event.is_set():
            print("\n[Encerrando conexão...]")
            self.stop_event.set()
            self.send_queue.put(None)  # sinaliza fim do generator
            
            if self.channel:
                try:
                    self.channel.close()
                except:
                    pass
    
    def run(self):
        """Método principal que inicia o cliente."""
        # Configurar handler para Ctrl+C
        signal.signal(signal.SIGINT, lambda s, f: self.shutdown())
        
        # Conectar ao servidor
        try:
            print(f"[Conectando ao servidor {self.server_address}...]")
            self.channel = grpc.insecure_channel(self.server_address)
            self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
            
            # Testar conexão
            grpc.channel_ready_future(self.channel).result(timeout=5)
            print("[Conectado com sucesso!]")
            
        except grpc.FutureTimeoutError:
            print(f"[Erro: Não foi possível conectar ao servidor em {self.server_address}]")
            return
        except Exception as e:
            print(f"[Erro ao conectar: {e}]")
            return
        
        # Iniciar stream bidirecional
        try:
            responses = self.stub.Chat(self.request_generator())
        except grpc.RpcError as e:
            print(f"[Erro ao iniciar chat: {e.code()}]")
            return
        
        # Iniciar thread de recebimento (para ver mensagens do servidor)
        receive_thread = threading.Thread(
            target=self.receive_messages, 
            args=(responses,), 
        )
        receive_thread.start()
        
        # Aguardar um pouco para receber mensagem de boas-vindas
        import time
        time.sleep(0.5)
        
        # Processo de autenticação
        if not self.authenticate():
            self.shutdown()
            return
        
        # Iniciar thread de envio (após autenticação)
        send_thread = threading.Thread(target=self.send_messages)
        send_thread.start()
        
        # Aguardar thread de recebimento (thread principal)
        receive_thread.join()
        
        # Aguardar thread de envio finalizar
        send_thread.join(timeout=2)
        print("[Desconectado]")


def import_time():
    """Helper para importar time"""
    import time
    return time.time()

def import_sleep(seconds):
    """Helper para sleep"""
    import time
    time.sleep(seconds)


def main():
    # Pode passar endereço customizado como argumento
    server_address = sys.argv[1] if len(sys.argv) > 1 else "localhost:50051"
    
    client = ChatClient(server_address)
    client.run()


if __name__ == "__main__":
    main()
