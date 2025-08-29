from pyrogram import Client, filters
from pymongo import MongoClient
import os
import aiohttp
import asyncio
from PIL import Image

# 🔹 Configs de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "telegram_logs")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

# 🔹 Conexão MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]
collection = db["messages"]

# 🔹 ID do bot oficial (ignorar mensagens dele)
BOT_OFICIAL_ID = 7436240400

async def send_to_n8n(data, media_path=None):
    try:
        async with aiohttp.ClientSession() as session:
            if media_path:
                with open(media_path, "rb") as f:
                    files = {"file": f}
                    await session.post(N8N_WEBHOOK_URL, data=data, timeout=30)
            else:
                await session.post(N8N_WEBHOOK_URL, data=data, timeout=30)
        print(f"[WEBHOOK] Mensagem enviada para n8n: {data}")
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")

async def convert_image(path):
    try:
        img = Image.open(path)
        img = img.convert("RGB")
        new_path = f"/tmp/{os.path.basename(path)}.jpeg"
        img.save(new_path, "JPEG")
        return new_path
    except Exception as e:
        print(f"[IMAGE CONVERT ERROR] {e}")
        return path

@Client.on_message(filters.all & ~filters.service)
async def log_message(client, message):
    try:
        me = await client.get_me()

        # 🚫 Ignora mensagens enviadas pelo próprio userbot
        if message.outgoing or (message.from_user and message.from_user.id == me.id):
            return

        # 🚫 Ignora mensagens do bot oficial
        if message.from_user and message.from_user.id == BOT_OFICIAL_ID:
            return

        # ✅ Pega texto ou legenda (pode ser vazio se for só mídia)
        text_content = message.text or message.caption or ""

        data = {
            "message_id": message.id,
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", None),
            "user_id": message.from_user.id if message.from_user else None,
            "username": message.from_user.username if message.from_user else None,
            "outgoing": message.outgoing,
            "text": text_content,
            "has_media": bool(message.media),
            "date": message.date.isoformat() if message.date else None,
        }

        # ✅ Evita duplicados
        if not collection.find_one({"chat_id": message.chat.id, "message_id": message.id}):
            collection.insert_one(data)
            print(f"[LOG] Mensagem salva no MongoDB: {data}")
        else:
            print(f"[LOG] Ignorado duplicado: chat_id={message.chat.id}, message_id={message.id}")

        # 🔥 Envia para n8n
        if N8N_WEBHOOK_URL:
            media_path = None
            try:
                if message.media:
                    # Download para /tmp do Heroku
                    media_path = await message.download(file_name=f"/tmp/{message.chat.id}_{message.id}")
                    # Converte imagem se for suportada
                    media_path = await convert_image(media_path)
                await send_to_n8n(data, media_path)
            finally:
                if media_path and os.path.exists(media_path):
                    os.remove(media_path)

    except Exception as e:
        print(f"[LOGGER ERROR] {e}")

