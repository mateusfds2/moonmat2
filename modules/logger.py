# modules/logger.py
import os
import json
import aiohttp
import asyncio
import tempfile
import logging
import traceback
from pyrogram import filters

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s - %(message)s")

# Configs de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB", "telegram_logs")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

# Conexão MongoDB
mongo_client = None
db = None
collection = None
if MongoClient and MONGO_URI:
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping')
        db = mongo_client[MONGO_DB_NAME]
        collection = db["messages"]
        logging.info("[MONGODB] Conexão estabelecida com sucesso.")
    except Exception as e:
        logging.error(f"[MONGODB ERRO] {e}")
        mongo_client = db = collection = None
else:
    logging.warning("[MONGODB] Mongo não configurado, logs não serão salvos no banco.")

UPLOAD_SEMAPHORE = asyncio.Semaphore(5)

async def send_to_webhook(data, media_path=None):
    if not N8N_WEBHOOK_URL:
        return

    try:
        async with UPLOAD_SEMAPHORE:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("json_data", json.dumps(data, ensure_ascii=False), content_type="application/json")
                if media_path and os.path.exists(media_path):
                    with open(media_path, "rb") as f:
                        form.add_field("file", f, filename=os.path.basename(media_path), content_type="application/octet-stream")
                async with session.post(N8N_WEBHOOK_URL, data=form, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status >= 400:
                        logging.error(f"[WEBHOOK] Erro {resp.status}: {await resp.text()}")
                    else:
                        logging.info(f"[WEBHOOK] Enviado com sucesso: {resp.status}")
    except Exception as e:
        logging.error(f"[WEBHOOK ERRO] {e}\n{traceback.format_exc()}")
    finally:
        if media_path and os.path.exists(media_path):
            try:
                os.remove(media_path)
            except OSError as e:
                logging.error(f"Erro ao remover arquivo temporário: {e}")


# Registro do handler como módulo do Moon Userbot
def register_logger(app):
    @app.on_message(filters.all)
    async def log_message(client, message):
        try:
            # Ignora mensagens enviadas pelo próprio userbot
            if message.outgoing:
                return

            text_content = message.text or message.caption or ""
            from_user = message.from_user or message.forward_from

            data = {
                "chat_id": message.chat.id,
                "chat_title": getattr(message.chat, "title", getattr(message.chat, 'first_name', None)),
                "message_id": message.id,
                "from_user_id": from_user.id if from_user else None,
                "username": from_user.username if from_user else None,
                "first_name": getattr(from_user, 'first_name', None) if from_user else None,
                "text": text_content,
                "has_media": bool(message.media),
                "media_type": str(message.media) if message.media else None,
                "date": message.date.isoformat() if message.date else None,
            }

            # Salva no MongoDB
            if collection is not None:
                try:
                    collection.insert_one(data.copy())
                    logging.info(f"[MONGODB] Mensagem do chat '{data['chat_title']}' salva.")
                except Exception as e:
                    logging.error(f"[MONGODB ERRO] {e}")

            # Baixa mídia se houver
            media_path = None
            if message.media:
                try:
                    temp_dir = tempfile.gettempdir()
                    media_path = await message.download(file_name=os.path.join(temp_dir, f"{message.chat.id}_{message.id}"))
                    logging.info(f"Mídia baixada: {media_path}")
                except Exception as e:
                    logging.error(f"[MEDIA ERRO] Falha ao baixar mídia: {e}")

            # Envia para webhook em background
            asyncio.create_task(send_to_webhook(data, media_path))

        except Exception as e:
            logging.error(f"[LOGGER ERRO] {e}\n{traceback.format_exc()}")
