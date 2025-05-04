import socket
import threading
import time
import base64
import os
import hashlib
import random

BROADCAST_IP = '255.255.255.255'
PORT = 50000
BUFFER_SIZE = 65535
HEARTBEAT_INTERVAL = 5
DEVICE_TIMEOUT = 10

# Guardar dispositivos conhecidos
devices = {}

# Socket UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('', PORT))
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

# Nome do dispositivo atual
device_name = input("Digite o nome do dispositivo: ")

def send_message(message, address=(BROADCAST_IP, PORT)):
    sock.sendto(message.encode(), address)

def receive_messages():
    while True:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            message = data.decode()
            handle_message(message, addr)
        except Exception as e:
            print(f"Erro ao receber: {e}")

def handle_message(message, addr):
    parts = message.split(' ', 2)
    command = parts[0]

    if command == 'HEARTBEAT':
        name = parts[1]
        devices[name] = {'address': addr, 'last_seen': time.time()}
    elif command == 'TALK':
        msg_id, content = parts[1], parts[2]
        print(f"\nMensagem recebida de {addr}: {content}")
        send_message(f"ACK {msg_id}", addr)
    elif command == 'ACK':
        print(f"ACK recebido para ID {parts[1]}")
    elif command == 'FILE':
        handle_file_request(parts, addr)
    elif command == 'CHUNK':
        handle_chunk(parts, addr)
    elif command == 'END':
        handle_end(parts, addr)
    elif command == 'NACK':
        print(f"NACK recebido: {message}")

# Funções para enviar e receber arquivos
file_transfer = {}

def handle_file_request(parts, addr):
    msg_id, filename, size = parts[1].split(' ', 2)
    file_transfer[msg_id] = {'filename': filename, 'size': int(size), 'chunks': {}, 'addr': addr}
    send_message(f"ACK {msg_id}", addr)

def handle_chunk(parts, addr):
    msg_id, rest = parts[1], parts[2]
    seq, data = rest.split(' ', 1)
    if msg_id in file_transfer:
        file_transfer[msg_id]['chunks'][int(seq)] = base64.b64decode(data)
        send_message(f"ACK {msg_id}", addr)

def handle_end(parts, addr):
    msg_id, received_hash = parts[1], parts[2]
    file_info = file_transfer.get(msg_id)
    if not file_info:
        return
    filename = file_info['filename']
    chunks = file_info['chunks']
    with open(f"received_{filename}", 'wb') as f:
        for i in sorted(chunks.keys()):
            f.write(chunks[i])
    # Verificar integridade
    hasher = hashlib.sha256()
    with open(f"received_{filename}", 'rb') as f:
        hasher.update(f.read())
    calculated_hash = hasher.hexdigest()
    if calculated_hash == received_hash:
        send_message(f"ACK {msg_id}", addr)
        print(f"Arquivo {filename} recebido com sucesso!")
    else:
        send_message(f"NACK {msg_id} hash_mismatch", addr)

def send_heartbeat():
    while True:
        send_message(f"HEARTBEAT {device_name}")
        time.sleep(HEARTBEAT_INTERVAL)

def remove_inactive_devices():
    while True:
        current_time = time.time()
        to_remove = [name for name, info in devices.items() if current_time - info['last_seen'] > DEVICE_TIMEOUT]
        for name in to_remove:
            del devices[name]
        time.sleep(1)

def command_interface():
    while True:
        cmd = input("\n> ").strip()
        if cmd == 'devices':
            print("\nDispositivos ativos:")
            for name, info in devices.items():
                print(f"{name} - {info['address'][0]}:{info['address'][1]} - {int(time.time() - info['last_seen'])}s atrás")
        elif cmd.startswith('talk'):
            parts = cmd.split(' ', 2)
            target_name, message = parts[1], parts[2]
            if target_name in devices:
                msg_id = str(random.randint(1000, 9999))
                send_message(f"TALK {msg_id} {message}", devices[target_name]['address'])
            else:
                print("Dispositivo não encontrado.")
        elif cmd.startswith('sendfile'):
            parts = cmd.split(' ', 2)
            target_name, filename = parts[1], parts[2]
            if target_name in devices:
                send_file(devices[target_name]['address'], filename)
            else:
                print("Dispositivo não encontrado.")

def send_file(addr, filename):
    if not os.path.exists(filename):
        print("Arquivo não encontrado.")
        return
    msg_id = str(random.randint(1000, 9999))
    size = os.path.getsize(filename)
    send_message(f"FILE {msg_id} {filename} {size}", addr)
    time.sleep(0.5)
    with open(filename, 'rb') as f:
        seq = 0
        while chunk := f.read(1024):
            b64_chunk = base64.b64encode(chunk).decode()
            send_message(f"CHUNK {msg_id} {seq} {b64_chunk}", addr)
            time.sleep(0.1)
            seq += 1
    # Enviar END
    hasher = hashlib.sha256()
    with open(filename, 'rb') as f:
        hasher.update(f.read())
    file_hash = hasher.hexdigest()
    send_message(f"END {msg_id} {file_hash}", addr)

def main():
    threading.Thread(target=receive_messages, daemon=True).start()
    threading.Thread(target=send_heartbeat, daemon=True).start()
    threading.Thread(target=remove_inactive_devices, daemon=True).start()
    command_interface()

if __name__ == "__main__":
    main()
