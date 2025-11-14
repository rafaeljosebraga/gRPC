import grpc
from concurrent import futures
import chat_pb2
import chat_pb2_grpc
import queue
import threading
import hashlib
from datetime import datetime

class ChatService(chat_pb2_grpc.ChatServiceServicer):
    def __init__(self):
        self.clients = {}
        self.clients_lock = threading.Lock()
        self.client_counter = 0
        self.users = {}
        self.users_lock = threading.Lock()
        self.message_history = {}
        self.history_lock = threading.Lock()
    
    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _authenticate_user(self, username, password):
        with self.users_lock:
            if username not in self.users:
                self.users[username] = self._hash_password(password)
                return True, "Registrado"
            else:
                if self.users[username] == self._hash_password(password):
                    return True, "Autenticado"
                return False, "Senha incorreta"
    
    def _save_message(self, username, text, is_sent=True):
        with self.history_lock:
            if username not in self.message_history:
                self.message_history[username] = []
            
            self.message_history[username].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'sent' if is_sent else 'received',
                'text': text
            })
            
            if len(self.message_history[username]) > 100:
                self.message_history[username] = self.message_history[username][-100:]
    
    def _get_history(self, username):
        with self.history_lock:
            if username not in self.message_history or not self.message_history[username]:
                return "Histórico vazio"
            
            lines = [f"=== Histórico de {username} ==="]
            for msg in self.message_history[username][-20:]:
                timestamp = datetime.fromisoformat(msg['timestamp']).strftime('%H:%M:%S')
                msg_type = "VOCÊ" if msg['type'] == 'sent' else "RECV"
                lines.append(f"[{timestamp}] {msg_type}: {msg['text']}")
            
            return "\n".join(lines)
    
    def Chat(self, request_iterator, context):
        client_queue = queue.Queue(maxsize=100)
        client_id = None
        username = None
        authenticated = False
        
        try:
            with self.clients_lock:
                self.client_counter += 1
                client_id = self.client_counter
                self.clients[client_id] = (client_queue, None)
            
            client_queue.put(("Sistema", "Autentique-se: USUARIO:SENHA"))
            
            def receive_messages():
                nonlocal username, authenticated
                try:
                    for incoming in request_iterator:
                        if not authenticated:
                            if ':' not in incoming.text:
                                client_queue.put(("Sistema", "Formato: USUARIO:SENHA"))
                                continue
                            
                            parts = incoming.text.split(':', 1)
                            if len(parts) != 2:
                                continue
                            
                            temp_username = parts[0].strip()
                            password = parts[1].strip()
                            
                            if not temp_username or not password:
                                continue
                            
                            success, message = self._authenticate_user(temp_username, password)
                            
                            if success:
                                username = temp_username
                                authenticated = True
                                
                                with self.clients_lock:
                                    self.clients[client_id] = (client_queue, username)
                                
                                client_queue.put(("Sistema", f"{message} | {username}"))
                                self.broadcast("Sistema", f"{username} entrou", exclude_client=client_id)
                            else:
                                client_queue.put(("Sistema", message))
                            
                            continue
                        
                        if incoming.text.strip().lower() == "/hist":
                            history = self._get_history(username)
                            client_queue.put(("Sistema", history))
                            continue
                        
                        self._save_message(username, incoming.text, is_sent=True)
                        self.broadcast_with_history(username, incoming.text, exclude_client=client_id)
                        
                except:
                    pass
                finally:
                    client_queue.put(None)
            
            receive_thread = threading.Thread(target=receive_messages)
            receive_thread.start()
            
            while context.is_active():
                try:
                    msg = client_queue.get(timeout=1.0)
                    
                    if msg is None:
                        break
                    
                    yield chat_pb2.Message(username=msg[0], text=msg[1])
                    
                except queue.Empty:
                    continue
                except:
                    break
            
            receive_thread.join(timeout=2)
            
        except:
            pass
            
        finally:
            saved_username = None
            should_notify = False
            
            with self.clients_lock:
                if client_id in self.clients:
                    _, saved_username = self.clients[client_id]
                    del self.clients[client_id]
                    
                    if saved_username and authenticated:
                        should_notify = True
            
            if should_notify:
                self.broadcast("Sistema", f"{saved_username} saiu", exclude_client=client_id)
    
    def broadcast(self, username, text, exclude_client=None):
        message = (username, text)
        
        with self.clients_lock:
            for client_id, (client_queue, _) in self.clients.items():
                if exclude_client is not None and client_id == exclude_client:
                    continue
                
                try:
                    client_queue.put_nowait(message)
                except:
                    pass
    
    def broadcast_with_history(self, sender_username, text, exclude_client=None):
        message = (sender_username, text)
        
        with self.clients_lock:
            for client_id, (client_queue, receiver_username) in self.clients.items():
                if exclude_client is not None and client_id == exclude_client:
                    continue
                
                if receiver_username is None:
                    continue
                
                try:
                    self._save_message(receiver_username, f"{sender_username}: {text}", is_sent=False)
                    client_queue.put_nowait(message)
                except:
                    pass


def serve(port=50051):
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.keepalive_time_ms', 10000),
            ('grpc.keepalive_timeout_ms', 5000),
        ]
    )
    
    chat_service = ChatService()
    chat_pb2_grpc.add_ChatServiceServicer_to_server(chat_service, server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    
    print(f"Servidor rodando na porta {port}")
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=5)


if __name__ == "__main__":
    serve()
