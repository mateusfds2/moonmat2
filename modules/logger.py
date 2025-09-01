import os
import json
import aiohttp
import asyncio
import tempfile
from pyrogram import Client, filters
from pymongo import MongoClient
import logging

# 🔹 Configuração de logs
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(message)s"
)

# 🔹 Configs de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "telegram_logs")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")  # já configurado no Heroku

# 🔹 MongoDB
mongo_client = MongoClient(MONGO_URI) if MONGO_URI else None
db = mongo_client[MONGO_DB] if mongo_client else None
collection = db["messages"] if db is not None else None  # ✅ Corrigido

# 🔹 Limite de uploads simultâneos
UPLOAD_SEMAPHORE = asyncio.Semaphore(3)


async def send_webhook(data, media_path=None):
    """Envia dados e arquivo para n8n usando aiohttp"""
    if not N8N_WEBHOOK_URL:
        return

    tmp_txt_path = None
    try:
        async with UPLOAD_SEMAPHORE:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()

                # Arquivo de mídia ou texto temporário
                if media_path and os.path.exists(media_path):
                    with open(media_path, "rb") as f:
                        form.add_field(
                            "file",
                            f,
                            filename=os.path.basename(media_path),
                            content_type="application/octet-stream"
                        )
                else:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp_txt:
                        tmp_txt_path = tmp_txt.name
                        tmp_txt.write(data.get("text", "").encode("utf-8"))

                    with open(tmp_txt_path, "rb") as f:
                        form.add_field(
                            "file",
                            f,
                            filename="message.txt",
                            content_type="text/plain"
                        )

                # Campos adicionais
                for k, v in data.items():
                    form.add_field(k, str(v))

                async with session.post(N8N_WEBHOOK_URL, data=form, timeout=60) as resp:
                    logging.info(f"[WEBHOOK] Status: {resp.status}")

    except Exception as e:
        logging.error(f"[WEBHOOK ERROR] {e}")
    finally:
        if media_path and os.path.exists(media_path):
            os.remove(media_path)
        if tmp_txt_path and os.path.exists(tmp_txt_path):
            os.remove(tmp_txt_path)


# 🔹 Pyrogram Client
app = Client(
    "moon_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)


@app.on_message(filters.all & ~filters.service)
async def log_message(client, message):
    try:
        me = await client.get_me()

        # Ignora mensagens enviadas pelo bot
        if message.outgoing or (message.from_user and message.from_user.id == me.id):
            return

        text_content = message.text or message.caption or ""

        data = {
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", None),
            "message_id": message.id,
            "from_user_id": message.from_user.id if message.from_user else None,
            "username": message.from_user.username if message.from_user else None,
            "text": text_content,
            "has_media": bool(message.media),
            "date": message.date.isoformat() if message.date else None,
        }

        # Salva no MongoDB
        if collection:
            if not collection.find_one({"chat_id": message.chat.id, "message_id": message.id}):
                result = collection.insert_one(data)
                data["_id"] = str(result.inserted_id)
                logging.info(f"[LOG] Mensagem salva no MongoDB: {data}")
            else:
                logging.info(f"[LOG] Ignorado duplicado: chat_id={message.chat.id}, message_id={message.id}")

        # Download da mídia
        media_path = None
        if message.media:
            media_path = await message.download(file_name=f"/tmp/{message.chat.id}_{message.id}")

        # Envia para o webhook sem bloquear
        asyncio.create_task(send_webhook(data, media_path))

    except Exception as e:
        logging.error(f"[LOGGER ERROR] {e}")


if __name__ == "__main__":
    logging.info("[START] Moon Userbot iniciado...")
    app.run()
