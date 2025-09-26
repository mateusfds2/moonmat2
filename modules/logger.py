from pyrogram import Client, filters
from pymongo import MongoClient
import os
import re

# 🔹 Configs de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "telegram_logs")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]
collection = db["messages"]

# 🔹 ID do seu bot oficial que não deve ser logado
BOT_OFICIAL_ID = 7436240400

# 🔹 Grupos de destino
FORWARD_CHAT_ID_1 = int(os.getenv("FORWARD_CHAT_ID", "-1002993843722"))
FORWARD_CHAT_ID_2 = -1003012964574  # segundo grupo

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
    if message.photo:
        # Para fotos, pega a maior resolução
        return max(photo.file_size for photo in message.photo.thumbs + [message.photo])
    elif message.document:
        return message.document.file_size
    elif message.video:
        return message.video.file_size
    elif message.audio:
        return message.audio.file_size
    elif message.voice:
        return message.voice.file_size
    elif message.video_note:
        return message.video_note.file_size
    elif message.sticker:
        return message.sticker.file_size
    elif message.animation:
        return message.animation.file_size
    return 0

@Client.on_message(filters.all & ~filters.service)
async def log_and_forward(client, message):
    try:
        # ❌ Ignora mensagens do BOT_OFICIAL
        if message.from_user and message.from_user.id == BOT_OFICIAL_ID:
            return

        # ✅ Pega texto ou legenda
        text_content = message.text or message.caption or ""
        
        # 🔎 Verifica se contém URL
        has_url = bool(URL_REGEX.search(text_content))
        
        # 📁 Verifica tamanho do arquivo
        file_size = get_file_size(message)
        
        # 🚫 Verifica se o arquivo excede o tamanho máximo
        if file_size > MAX_FILE_SIZE:
            print(f"[BLOQUEADO] Arquivo muito grande ({format_file_size(file_size)}) - máximo permitido: {format_file_size(MAX_FILE_SIZE)}")
            return
        
        # 🚫 Bloqueia tudo que não for texto, foto ou URL
        if not (message.text or message.photo or has_url):
            print(f"[IGNORADO] Mensagem {message.id} não é texto, imagem ou URL.")
            return

        # 📊 Prepara dados para o MongoDB
        data = {
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", None),
            "message_id": message.id,
            "from_user_id": getattr(message.from_user, "id", None) if message.from_user else None,
            "username": getattr(message.from_user, "username", None) if message.from_user else None,
            "outgoing": message.outgoing,
            "text": text_content,
            "has_media": bool(message.photo),  # só marca mídia se for imagem
            "file_size": file_size if file_size > 0 else None,  # adiciona tamanho do arquivo
            "date": message.date.isoformat() if message.date else None,
        }

        # ✅ Evita duplicados
        if not collection.find_one({"chat_id": message.chat.id, "message_id": message.id}):
            collection.insert_one(data)
            size_info = f" ({format_file_size(file_size)})" if file_size > 0 else ""
            print(f"[LOG] Mensagem salva no MongoDB{size_info}: {data}")
        else:
            print(f"[LOG] Ignorado duplicado: chat_id={message.chat.id}, message_id={message.id}")

        # 🔥 Encaminha para os grupos de destino
        for forward_id in [FORWARD_CHAT_ID_1, FORWARD_CHAT_ID_2]:
            try:
                await message.forward(forward_id)
                size_info = f" ({format_file_size(file_size)})" if file_size > 0 else ""
                print(f"[FORWARD] Mensagem {message.id}{size_info} encaminhada para {forward_id}")
            except Exception as e:
                print(f"[FORWARD ERROR] {e} ao tentar encaminhar para {forward_id}")

    except Exception as e:
        print(f"[LOGGER ERROR] {e}")
