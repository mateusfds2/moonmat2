from pyrogram import Client, filters
from pymongo import MongoClient
import os
import aiohttp
import asyncio
import tempfile

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
    files = None
    try:
        async with UPLOAD_SEMAPHORE:
            async with aiohttp.ClientSession() as session:
                if media_path:
                    with open(media_path, "rb") as f:
                        form = aiohttp.FormData()
                        form.add_field("file", f, filename=os.path.basename(media_path))
                        for k, v in data.items():
                            form.add_field(k, str(v))
                        async with session.post(N8N_WEBHOOK_URL, data=form, timeout=30) as resp:
                            print(f"[WEBHOOK] Status: {resp.status}")
                else:
                    async with session.post(N8N_WEBHOOK_URL, data=data, timeout=30) as resp:
                        print(f"[WEBHOOK] Status: {resp.status}")
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")
    finally:
        if media_path and os.path.exists(media_path):
            os.remove(media_path)  # Remove arquivo temporário

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

        # ✅ Pega texto ou legenda (pode ser vazio se for só mídia)
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

        # 🔥 Envia para n8n
        media_path = None
        if message.media:
            # Usa arquivo temporário
            tmp_file = tempfile.NamedTemporaryFile(delete=False)
            media_path = await message.download(file_name=tmp_file.name)
        asyncio.create_task(send_webhook(data, media_path))

    except Exception as e:
        print(f"[LOGGER ERROR] {e}")
