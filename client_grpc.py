import grpc
import threading
import queue
import sys
import signal
import time
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
        
    def request_generator(self):
        while not self.stop_event.is_set():
            try:
                message = self.send_queue.get(timeout=0.1)
                if message is None:
                    break
                yield chat_pb2.Message(username=self.username or "unknown", text=message)
            except queue.Empty:
                continue
    
    def send_messages(self):
        while not self.authenticated and not self.stop_event.is_set():
            time.sleep(0.1)
        
        if self.stop_event.is_set():
            return
        
        print("\nChat iniciado. Digite /quit para sair, /hist para histórico\n")
        
        while not self.stop_event.is_set():
            try:
                text = input()
                if self.stop_event.is_set():
                    break
                    
                if text.lower() == "/quit":
                    self.shutdown()
                    break
                    
                if text.strip():
                    self.send_queue.put(text)
                    
            except (EOFError, KeyboardInterrupt):
                self.shutdown()
                break
    
    def receive_messages(self, responses):
        try:
            for response in responses:
                if self.stop_event.is_set():
                    break
                
                if response.username == "Sistema":
                    print(f"\n[Sistema] {response.text}")
                    
                    if ("Registrado" in response.text or "Autenticado" in response.text) and not self.authenticated:
                        self.authenticated = True
                else:
                    if response.username != self.username:
                        print(f"\n{response.username}: {response.text}")
                    
        except grpc.RpcError:
            if not self.stop_event.is_set():
                print("\nConexão perdida")
        finally:
            self.shutdown()
    
    def authenticate(self):
        print("\n=== Autenticação ===")
        
        try:
            username = input("Usuário: ").strip()
            if not username:
                return False
            
            password = input("Senha: ").strip()
            if not password:
                return False
            
            self.username = username
            self.send_queue.put(f"{username}:{password}")
            
            timeout = 10
            start = time.time()
            
            while not self.authenticated and not self.stop_event.is_set():
                if time.time() - start > timeout:
                    print("Timeout")
                    return False
                time.sleep(0.1)
            
            return self.authenticated
            
        except (EOFError, KeyboardInterrupt):
            return False
    
    def shutdown(self):
        if not self.stop_event.is_set():
            print("\nEncerrando...")
            self.stop_event.set()
            self.send_queue.put(None)
            
            if self.channel:
                try:
                    self.channel.close()
                except:
                    pass
    
    def run(self):
        signal.signal(signal.SIGINT, lambda s, f: self.shutdown())
        
        try:
            print(f"Conectando a {self.server_address}...")
            self.channel = grpc.insecure_channel(self.server_address)
            self.stub = chat_pb2_grpc.ChatServiceStub(self.channel)
            grpc.channel_ready_future(self.channel).result(timeout=5)
            print("Conectado")
            
        except:
            print("Erro ao conectar")
            return
        
        try:
            responses = self.stub.Chat(self.request_generator())
        except:
            print("Erro ao iniciar chat")
            return
        
        receive_thread = threading.Thread(target=self.receive_messages, args=(responses,))
        receive_thread.start()
        
        time.sleep(0.5)
        
        if not self.authenticate():
            self.shutdown()
            return
        
        send_thread = threading.Thread(target=self.send_messages)
        send_thread.start()
        
        receive_thread.join()
        send_thread.join(timeout=2)
        print("Desconectado")


def main():
    server_address = sys.argv[1] if len(sys.argv) > 1 else "localhost:50051"
    client = ChatClient(server_address)
    client.run()


if __name__ == "__main__":
    main()
