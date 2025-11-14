import grpc
from concurrent import futures
import chat_pb2
import chat_pb2_grpc
import queue
import threading
import time
import logging
import hashlib
import json
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChatService(chat_pb2_grpc.ChatServiceServicer):
    def __init__(self):
        self.clients = {}  # {client_id: (queue, username)}
        self.clients_lock = threading.Lock()
        self.client_counter = 0
        
        # Autenticação: {username: password_hash}
        self.users = {}
        self.users_lock = threading.Lock()
        
        # Histórico: {username: [messages]}
        self.message_history = {}
        self.history_lock = threading.Lock()
        
        logger.info("Sistema de autenticação e histórico inicializado")
    
    def _hash_password(self, password):
        """Hash simples de senha (SHA256)"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _authenticate_user(self, username, password):
        """
        Autentica usuário.
        Retorna: (success: bool, message: str)
        """
        with self.users_lock:
            if username not in self.users:
                # PRIMEIRO LOGIN: Registrar usuário
                self.users[username] = self._hash_password(password)
                logger.info(f"Novo usuário registrado: '{username}'")
                return True, "Usuário registrado com sucesso!"
            else:
                # JÁ EXISTE: Verificar senha
                stored_hash = self.users[username]
                provided_hash = self._hash_password(password)
                
                if stored_hash == provided_hash:
                    logger.info(f"Usuário autenticado: '{username}'")
                    return True, "Autenticado com sucesso!"
                else:
                    logger.warning(f"Falha na autenticação: '{username}'")
                    return False, "Senha incorreta!"
    
    def _save_message(self, username, text, is_sent=True):
        """
        Salva mensagem no histórico.
        is_sent: True se o usuário enviou, False se recebeu
        """
        with self.history_lock:
            if username not in self.message_history:
                self.message_history[username] = []
            
            message_record = {
                'timestamp': datetime.now().isoformat(),
                'type': 'sent' if is_sent else 'received',
                'from': username if is_sent else 'other',
                'text': text
            }
            
            self.message_history[username].append(message_record)
            
            # Limitar histórico a 100 mensagens por usuário
            if len(self.message_history[username]) > 100:
                self.message_history[username] = self.message_history[username][-100:]
    
    def _get_history(self, username):
        """
        Retorna histórico formatado do usuário.
        """
        with self.history_lock:
            if username not in self.message_history:
                return "Nenhum histórico encontrado."
            
            messages = self.message_history[username]
            if not messages:
                return "Histórico vazio."
            
            # Formatar histórico
            lines = [f"=== Histórico de {username} ({len(messages)} mensagens) ==="]
            
            for msg in messages[-20:]:  # Últimas 20 mensagens
                timestamp = datetime.fromisoformat(msg['timestamp']).strftime('%H:%M:%S')
                msg_type = "VOCÊ" if msg['type'] == 'sent' else "RECEBIDO"
                lines.append(f"[{timestamp}] {msg_type}: {msg['text']}")
            
            lines.append("=" * 50)
            return "\n".join(lines)
    
    def Chat(self, request_iterator, context):
        """Gerencia conexão bidirecional de um cliente."""
        client_queue = queue.Queue(maxsize=100)
        client_id = None
        username = None
        authenticated = False
        
        try:
            # Registrar cliente (ainda não autenticado)
            with self.clients_lock:
                self.client_counter += 1
                client_id = self.client_counter
                self.clients[client_id] = (client_queue, None)
            
            logger.info(f"Cliente {client_id} conectado (não autenticado)")
            
            # Enviar mensagem de boas-vindas
            client_queue.put(("Sistema", "Bem-vindo ao chat! Por favor, autentique-se."))
            client_queue.put(("Sistema", "Formato: USUARIO:SENHA (ex: joao:minhasenha)"))
            
            # Thread para receber mensagens do cliente
            def receive_messages():
                nonlocal username, authenticated
                try:
                    for incoming in request_iterator:
                        # FASE 1: AUTENTICAÇÃO
                        if not authenticated:
                            # Espera formato: USERNAME:PASSWORD
                            if ':' not in incoming.text:
                                client_queue.put(("Sistema", "Formato inválido! Use: USUARIO:SENHA"))
                                continue
                            
                            parts = incoming.text.split(':', 1)
                            if len(parts) != 2:
                                client_queue.put(("Sistema", "Formato inválido! Use: USUARIO:SENHA"))
                                continue
                            
                            temp_username = parts[0].strip()
                            password = parts[1].strip()
                            
                            if not temp_username or not password:
                                client_queue.put(("Sistema", "Usuário e senha não podem ser vazios!"))
                                continue
                            
                            # Tentar autenticar
                            success, message = self._authenticate_user(temp_username, password)
                            
                            if success:
                                username = temp_username
                                authenticated = True
                                
                                # Atualizar registro do cliente
                                with self.clients_lock:
                                    self.clients[client_id] = (client_queue, username)
                                
                                client_queue.put(("Sistema", message))
                                client_queue.put(("Sistema", f"Bem-vindo, {username}!"))
                                client_queue.put(("Sistema", "Use /hist para ver seu histórico"))
                                
                                # Notificar outros usuários
                                self.broadcast(
                                    "Sistema",
                                    f"{username} entrou no chat",
                                    exclude_client=client_id
                                )
                            else:
                                client_queue.put(("Sistema", f"ERRO: {message}"))
                                # Não desconecta, permite tentar novamente
                            
                            continue
                        
                        # FASE 2: CHAT NORMAL (já autenticado)
                        
                        # Comando /hist
                        if incoming.text.strip().lower() == "/hist":
                            history = self._get_history(username)
                            client_queue.put(("Sistema", history))
                            continue
                        
                        # Comando /help
                        if incoming.text.strip().lower() == "/help":
                            help_text = (
                                "Comandos disponíveis:\n"
                                "  /hist  - Ver histórico de mensagens\n"
                                "  /help  - Mostrar esta ajuda\n"
                                "  /quit  - Sair do chat"
                            )
                            client_queue.put(("Sistema", help_text))
                            continue
                        
                        # Mensagem normal
                        logger.info(f"[{username}]: {incoming.text}")
                        
                        # Salvar no histórico do remetente
                        self._save_message(username, incoming.text, is_sent=True)
                        
                        # Broadcast para outros (e salvar no histórico deles)
                        self.broadcast_with_history(username, incoming.text, exclude_client=client_id)
                        
                except grpc.RpcError as e:
                    # RpcError pode não ter .code() em alguns casos
                    try:
                        error_code = e.code() if hasattr(e, 'code') else 'UNKNOWN'
                        logger.warning(f"Cliente {client_id} desconectado: {error_code}")
                    except:
                        logger.warning(f"Cliente {client_id} desconectado (RPC error)")
                except Exception as e:
                    logger.error(f"Erro ao receber de cliente {client_id}: {e}")
                finally:
                    # Sinalizar fim da conexão
                    client_queue.put(None)
            
            # Iniciar thread de recebimento
            receive_thread = threading.Thread(target=receive_messages)
            receive_thread.start()
            
            # Loop principal: enviar mensagens ao cliente
            while context.is_active():
                try:
                    # Aguardar mensagem na fila (com timeout)
                    msg = client_queue.get(timeout=1.0)
                    
                    if msg is None:  # sinal de encerramento
                        break
                    
                    # Enviar mensagem ao cliente
                    yield chat_pb2.Message(username=msg[0], text=msg[1])
                    
                except queue.Empty:
                    # Timeout - verifica se conexão ainda está ativa
                    continue
                except Exception as e:
                    logger.error(f"Erro ao enviar para cliente {client_id}: {e}")
                    break
            
            # Aguardar thread de recebimento
            receive_thread.join(timeout=2)
            
        except Exception as e:
            logger.error(f"Erro no cliente {client_id}: {e}")
            
        finally:
            # Remover cliente e notificar saída
            with self.clients_lock:
                if client_id in self.clients:
                    _, saved_username = self.clients[client_id]
                    del self.clients[client_id]
                    logger.info(f"Cliente {client_id} removido ({len(self.clients)} ativos)")
                    
                    if saved_username and authenticated:
                        self.broadcast(
                            "Sistema",
                            f"{saved_username} saiu do chat",
                            exclude_client=client_id
                        )
    
    def broadcast(self, username, text, exclude_client=None):
        """
        Envia mensagem para todos os clientes conectados.
        """
        message = (username, text)
        failed_clients = []
        
        with self.clients_lock:
            for client_id, (client_queue, _) in self.clients.items():
                # Pular cliente excluído
                if exclude_client is not None and client_id == exclude_client:
                    continue
                
                try:
                    # Tentar enviar sem bloquear
                    client_queue.put_nowait(message)
                except queue.Full:
                    logger.warning(f"Fila do cliente {client_id} cheia, mensagem descartada")
                    failed_clients.append(client_id)
                except Exception as e:
                    logger.error(f"Erro ao enfileirar para cliente {client_id}: {e}")
                    failed_clients.append(client_id)
        
        # Limpar clientes com problemas (fora do lock)
        for client_id in failed_clients:
            try:
                with self.clients_lock:
                    if client_id in self.clients:
                        self.clients[client_id][0].put(None)
            except:
                pass
    
    def broadcast_with_history(self, sender_username, text, exclude_client=None):
        """
        Broadcast que também salva no histórico dos receptores.
        """
        message = (sender_username, text)
        
        with self.clients_lock:
            for client_id, (client_queue, receiver_username) in self.clients.items():
                # Pular cliente excluído
                if exclude_client is not None and client_id == exclude_client:
                    continue
                
                # Pular se não autenticado
                if receiver_username is None:
                    continue
                
                try:
                    # Salvar no histórico do receptor
                    self._save_message(receiver_username, f"{sender_username}: {text}", is_sent=False)
                    
                    # Enviar mensagem
                    client_queue.put_nowait(message)
                except queue.Full:
                    logger.warning(f"Fila do cliente {client_id} cheia")
                except Exception as e:
                    logger.error(f"Erro ao processar para cliente {client_id}: {e}")
    
    def get_stats(self):
        """Retorna estatísticas do servidor."""
        with self.clients_lock:
            authenticated_users = [username for _, username in self.clients.values() if username]
        
        with self.users_lock:
            total_users = len(self.users)
        
        with self.history_lock:
            total_messages = sum(len(msgs) for msgs in self.message_history.values())
        
        return {
            'connected_clients': len(self.clients),
            'authenticated_users': authenticated_users,
            'total_registered_users': total_users,
            'total_messages_stored': total_messages
        }


def serve(port=50051, max_workers=10):
    """Inicia o servidor gRPC."""
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=[
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
            ('grpc.keepalive_time_ms', 10000),
            ('grpc.keepalive_timeout_ms', 5000),
        ]
    )
    
    chat_service = ChatService()
    chat_pb2_grpc.add_ChatServiceServicer_to_server(chat_service, server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    
    logger.info(f"Servidor gRPC rodando na porta {port}...")
    logger.info(f"Workers: {max_workers}")
    logger.info("Recursos: Autenticação + Histórico de Mensagens")
    
    # Thread para imprimir estatísticas periodicamente
    def print_stats():
        while True:
            time.sleep(30)
            stats = chat_service.get_stats()
            logger.info(
                f"Stats - Conectados: {stats['connected_clients']} | "
                f"Usuários: {stats['authenticated_users']} | "
                f"Total registrados: {stats['total_registered_users']} | "
                f"Mensagens armazenadas: {stats['total_messages_stored']}"
            )
    
    stats_thread = threading.Thread(target=print_stats)
    stats_thread.start()
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Encerrando servidor...")
        server.stop(grace=5)


if __name__ == "__main__":
    serve()
