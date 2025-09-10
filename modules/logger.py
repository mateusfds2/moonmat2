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
FORWARD_CHAT_ID_2 = -1004902774074  # segundo grupo

# 🔹 Regex para detectar URLs
URL_REGEX = re.compile(r'https?://\S+|www\.\S+')

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

        # 🚫 Bloqueia tudo que não for texto, foto ou URL
        if not (message.text or message.photo or has_url):
            print(f"[IGNORADO] Mensagem {message.id} não é texto, imagem ou URL.")
            return

        data = {
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", None),
            "message_id": message.id,
            "from_user_id": getattr(message.from_user, "id", None) if message.from_user else None,
            "username": getattr(message.from_user, "username", None) if message.from_user else None,
            "outgoing": message.outgoing,
            "text": text_content,
            "has_media": bool(message.photo),  # só marca mídia se for imagem
            "date": message.date.isoformat() if message.date else None,
        }

        # ✅ Evita duplicados
        if not collection.find_one({"chat_id": message.chat.id, "message_id": message.id}):
            collection.insert_one(data)
            print(f"[LOG] Mensagem salva no MongoDB: {data}")
        else:
            print(f"[LOG] Ignorado duplicado: chat_id={message.chat.id}, message_id={message.id}")

        # 🔥 Encaminha para os grupos de destino
        for forward_id in [FORWARD_CHAT_ID_1, FORWARD_CHAT_ID_2]:
            try:
                await message.forward(forward_id)
                print(f"[FORWARD] Mensagem {message.id} encaminhada para {forward_id}")
            except Exception as e:
                print(f"[FORWARD ERROR] {e} ao tentar encaminhar para {forward_id}")

    except Exception as e:
        print(f"[LOGGER ERROR] {e}")
