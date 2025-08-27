from pyrogram import Client, filters
from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "telegram_logs")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]
collection = db["messages"]

# ID do seu bot oficial que não deve ser logado
BOT_OFICIAL_ID = 7436240400

@Client.on_message(filters.all & ~filters.service)
async def log_message(client, message):
    try:
        me = await client.get_me()  # userbot rodando o logger

        # 🚫 Ignora mensagens enviadas pelo próprio userbot
        if message.outgoing or (message.from_user and message.from_user.id == me.id):
            return

        # 🚫 Ignora mensagens enviadas pelo bot oficial
        if message.from_user and message.from_user.id == BOT_OFICIAL_ID:
            return

        # ✅ Pega texto ou legenda (ignora se não houver)
        text_content = message.text or message.caption
        if not text_content:
            return

        data = {
            "message_id": message.id,
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", None),
            "user_id": getattr(message.from_user, "id", None) if message.from_user else None,
            "username": getattr(message.from_user, "username", None) if message.from_user else None,
            "outgoing": message.outgoing,
            "text": text_content,
            "has_media": bool(message.media),
            "date": message.date.isoformat() if message.date else None,
        }

        # ✅ evita duplicados usando chat_id + message_id
        if not collection.find_one({"chat_id": message.chat.id, "message_id": message.id}):
            collection.insert_one(data)
            print(f"[LOG] Mensagem salva no MongoDB: {data}")
        else:
            print(f"[LOG] Ignorado duplicado: chat_id={message.chat.id}, message_id={message.id}")

    except Exception as e:
        print(f"Erro ao salvar no MongoDB: {e}")
