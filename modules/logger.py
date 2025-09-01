from pyrogram import Client, filters
from pymongo import MongoClient
import os
import aiohttp
import asyncio
import tempfile
import json

# 🔹 Configs de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "telegram_logs")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

# 🔹 Conexão MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]
collection = db["messages"]

# 🔹 ID do seu bot oficial (ignorar mensagens dele)
BOT_OFICIAL_ID = 7436240400

# 🔹 Limite de uploads simultâneos
UPLOAD_SEMAPHORE = asyncio.Semaphore(3)


async def send_webhook(data, media_path=None):
    """Envia dados e arquivo para n8n usando aiohttp"""
    if not N8N_WEBHOOK_URL:
        return
    try:
        async with UPLOAD_SEMAPHORE:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()

                # ✅ Se tiver arquivo, manda como binário
                if media_path:
                    with open(media_path, "rb") as f:
                        form.add_field(
                            "file",
                            f,
                            filename=os.path.basename(media_path),
                            content_type="application/octet-stream"
                        )

                # ✅ Payload JSON em campo único
                form.add_field(
                    "payload_json",
                    json.dumps(data, ensure_ascii=False),
                    content_type="application/json"
                )

                async with session.post(N8N_WEBHOOK_URL, data=form, timeout=60) as resp:
