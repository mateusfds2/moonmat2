import os
import json
import aiohttp
import asyncio
import tempfile
from pyrogram import Client, filters
from pymongo import MongoClient

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
collection = db["messages"] if db else None

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

                if media_path and os.path.exists(media_path):
                    form.add_field(
                        "file",
                        open(media_path, "rb"),
                        filename=os.path.basename(media_path),
                        content_type="application/octet-stream"
                    )
                else:
                    tmp_txt = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
                    tmp_txt_path = tmp_txt.name
                    with open(tmp_txt_path, "w", encoding="utf-8") as f:
                        f.write(data.get("text", ""))

                    form.add_field(
                        "file",
                        open(tmp_txt_path, "rb"),
                        filename="message.txt",
                        content_type="text/plain"
                    )

                for k, v in data.items():
                    form.add_field(k, str(v))

                async with session.post(N8N_WEBHOOK_URL, data=form, timeout=60) as resp:
                    print(f"[WEBHOOK] Status: {resp.status}")
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")
    finally:
        if media_path and os.path.exists(media_path):
            os.remove(media_path)
        if tmp_txt_path and os.path.exists(tmp_txt_path):
            os.remove(tmp_txt_path)


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

        if collection:
            if not collection.find_one({"chat_id": message.chat.id, "message_id": message.id}):
                result = collection.insert_one(data)
                data["_id"] = str(result.inserted_id)
                print(f"[LOG] Mensagem salva no MongoDB: {data}")
            else:
                print(f"[LOG] Ignorado duplicado: chat_id={message.chat.id}, message_id={message.id}")

        media_path = None
        if message.media:
            media_path = await message.download(
                file_name=f"/tmp/{message.chat.id}_{message.id}"
            )

        asyncio.create_task(send_webhook(data, media_path))

    except Exception as e:
        print(f"[LOGGER ERROR] {e}")


if __name__ == "__main__":
    print("[START] Moon Userbot iniciado...")
    app.run()
