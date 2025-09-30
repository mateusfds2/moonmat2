from pyrogram import Client, filters
import os
import re

# 🔹 ID do seu bot oficial que não deve ser logado
BOT_OFICIAL_ID = 7436240400

# 🔹 Grupo que deve ser ignorado (não encaminhar mensagens)
BLOCKED_CHAT_ID = -1003047757269

# 🔹 Grupos de destino
FORWARD_CHAT_ID_1 = int(os.getenv("FORWARD_CHAT_ID", "-1002993843722"))

# 🔹 Tamanho máximo do arquivo em bytes (10MB)
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))  # 10MB por padrão

# 🔹 Regex para detectar URLs
URL_REGEX = re.compile(r'https?://\S+|www\.\S+')

def format_file_size(size_bytes):
    """Converte bytes para formato legível"""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes} bytes"

def get_file_size(message):
    """Retorna o tamanho do arquivo em bytes, se existir"""
    try:
        if message.photo:
            # Para fotos, usar apenas o file_size da photo principal
            return getattr(message.photo, 'file_size', 0)
        elif message.document:
            return getattr(message.document, 'file_size', 0)
        elif message.video:
            return getattr(message.video, 'file_size', 0)
        elif message.audio:
            return getattr(message.audio, 'file_size', 0)
        elif message.voice:
            return getattr(message.voice, 'file_size', 0)
        elif message.video_note:
            return getattr(message.video_note, 'file_size', 0)
        elif message.sticker:
            return getattr(message.sticker, 'file_size', 0)
        elif message.animation:
            return getattr(message.animation, 'file_size', 0)
        return 0
    except Exception as e:
        print(f"[ERROR] Erro ao obter tamanho do arquivo: {e}")
        return 0

@Client.on_message(filters.all & ~filters.service)
async def log_and_forward(client, message):
    try:
        # ❌ Ignora mensagens do BOT_OFICIAL
        if message.from_user and message.from_user.id == BOT_OFICIAL_ID:
            return

        # ❌ Ignora mensagens do grupo bloqueado
        if message.chat.id == BLOCKED_CHAT_ID:
            print(f"[BLOQUEADO] Mensagem do grupo ignorado: {BLOCKED_CHAT_ID}")
            return

        # ✅ Pega texto ou legenda com proteção contra None
        text_content = message.text or message.caption or ""
        
        # 🔎 Verifica se contém URL
        has_url = bool(URL_REGEX.search(text_content)) if text_content else False
        
        # 📁 Verifica tamanho do arquivo (com tratamento de erro)
        file_size = get_file_size(message)
        
        # 🚫 Verifica se o arquivo excede o tamanho máximo
        if file_size > MAX_FILE_SIZE:
            print(f"[BLOQUEADO] Arquivo muito grande ({format_file_size(file_size)}) - máximo permitido: {format_file_size(MAX_FILE_SIZE)}")
            return
        
        # 🚫 Bloqueia tudo que não for texto, foto ou URL (filtro restritivo)
        has_acceptable_content = (
            message.text or          # Mensagens de texto
            message.photo or         # Imagens/fotos
            has_url                  # Qualquer conteúdo com URL (texto ou legenda)
        )
        
        if not has_acceptable_content:
            print(f"[IGNORADO] Mensagem {message.id} não é texto, imagem ou URL.")
            return

        # 📋 Log da mensagem processada
        size_info = f" ({format_file_size(file_size)})" if file_size > 0 else ""
        print(f"[PROCESSANDO] Mensagem {message.id}{size_info} - Conteúdo: {text_content[:50]}...")

        # 🔥 Encaminha para os grupos de destino
        for forward_id in [FORWARD_CHAT_ID_1, FORWARD_CHAT_ID_2]:
            try:
                await message.forward(forward_id)
                print(f"[FORWARD] Mensagem {message.id}{size_info} encaminhada para {forward_id}")
            except Exception as e:
                print(f"[FORWARD ERROR] {e} ao tentar encaminhar para {forward_id}")

    except Exception as e:
        print(f"[LOGGER ERROR] Erro geral na função: {e}")
        # Log adicional para debug
        print(f"[DEBUG] Message ID: {getattr(message, 'id', 'unknown')}, Chat: {getattr(message.chat, 'id', 'unknown') if hasattr(message, 'chat') else 'unknown'}")
