# modules/logger.py
from pyrogram import Client, filters
from pymongo import MongoClient
import os
import aiohttp
import asyncio

# 🔹 Configs de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "telegram_logs")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

# 🔹 Conexão MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]
collection = db["messages"]

# 🔹 ID do bot oficial que não deve ser logado
BOT_OFICIAL_ID = 7436240400

@Client.on_message(filters.all & ~filters.service)
async def log_message(client, message):
    try:
        me = await client.get_me()

        # 🚫 Ignora mensagens enviadas pelo próprio userbot
        if message.outgoing or (message.from_user and message.from_user.id == me.id):
            return

        # 🚫 Ignora mensagens enviadas pelo bot oficial
        if message.from_user and message.from_user.id == BOT_OFICIAL_ID:
            return

        # ✅ Texto ou legenda (pode ser vazio se for só mídia)
        text_content = message.text or message.caption or ""

        data = {
            "chat_id": message.chat.id,
            "message_id": message.id,
            "from_user_id": message.from_user.id if message.from_user else None,
            "text": text_content,
            "date": message.date.isoformat() if message.date else None,
        }

        # ✅ Evita duplicados
        if not collection.find_one({"chat_id": message.chat.id, "message_id": message.id}):
            collection.insert_one(data)
            print(f"[LOG] Mensagem salva no MongoDB: {data}")
        else:
            print(f"[LOG] Ignorado duplicado: chat_id={message.chat.id}, message_id={message.id}")

        # 🔥 Dispara webhook async para n8n
        if N8N_WEBHOOK_URL:
            await send_to_n8n(message, data)

    except Exception as e:
        print(f"[LOGGER ERROR] {e}")


async def send_to_n8n(message, data):
    try:
        files = None
        # Se houver mídia
        if message.media:
            # Baixa para /tmp (Heroku)
            media_path = await message.download(file_name=f"/tmp/{message.chat.id}_{message.id}")
            files = {"file": open(media_path, "rb")}

        async with aiohttp.ClientSession() as session:
            if files:
                with files["file"] as f:
                    form = aiohttp.FormData()
                    form.add_field("file", f)
                    for k, v in data.items():
                        form.add_field(k, str(v))
                    async with session.post(N8N_WEBHOOK_URL, data=form, timeout=15) as resp:
                        print(f"[WEBHOOK] Status: {resp.status}")
            else:
                async with session.post(N8N_WEBHOOK_URL, data=data, timeout=15) as resp:
                    print(f"[WEBHOOK] Status: {resp.status}")
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")
    finally:
        if files:
            files["file"].close()
