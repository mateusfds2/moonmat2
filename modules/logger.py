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

# Configuração básica de logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s - %(message)s")

# Configurações de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB", "telegram_logs")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

# Conexão MongoDB
mongo_client = db = collection = None
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

# Limite de uploads simultâneos
UPLOAD_SEMAPHORE = asyncio.Semaphore(5)


async def send_to_webhook(data, media_path=None):
    """Envia dados para o n8n via webhook"""
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


def register_logger(app):
    """Registra o handler de mensagens no Moon Userbot"""
    @app.on_message(filters.all)
    async def log_message(client, message):
        try:
            if message.outgoing:
                return

            text_content = message.text or message.caption or ""

            # Detecta remetente: user, forward ou canal
            if message.from_user:
                from_user_id = message.from_user.id
                username = message.from_user.username
                first_name = getattr(message.from_user, 'first_name', None)
            elif message.forward_from:
                from_user_id = message.forward_from.id
                username = message.forward_from.username
                first_name = getattr(message.forward_from, 'first_name', None)
            elif message.forward_from_chat:
                from_user_id = message.forward_from_chat.id
                username = getattr(message.forward_from_chat, 'username', None)
                first_name = getattr(message.forward_from_chat, 'title', None)
            else:
                from_user_id = username = first_name = None

            data = {
                "chat_id": message.chat.id,
                "chat_title": getattr(message.chat, "title", getattr(message.chat, 'first_name', None)),
                "message_id": message.id,
                "from_user_id": from_user_id,
                "username": username,
                "first_name": first_name,
                "text": text_content,
                "has_media": bool(message.media),
                "media_type": str(message.media) if message.media else None,
                "date": message.date.isoformat() if message.date else None,
            }

            # Salva no MongoDB
            if collection is not None:
                try:
                    collection.insert_one(data.copy())
                    logging.info(f"[MONGODB] Mensagem salva: {data}")
                except Exception as e:
                    logging.error(f"[MONGODB ERRO] {e}")

            # Baixa mídia, se existir
            media_path = None
            if message.media:
                try:
                    temp_dir = tempfile.gettempdir()
                    media_path = await message.download(file_name=os.path.join(temp_dir, f"{message.chat.id}_{message.id}"))
                    logging.info(f"Mídia baixada: {media_path}")
                except Exception as e:
                    logging.error(f"[MEDIA ERRO] Falha ao baixar mídia: {e}")

            # Envia webhook em background
            asyncio.create_task(send_to_webhook(data, media_path))

        except Exception as e:
            logging.error(f"[LOGGER ERRO] {e}\n{traceback.format_exc()}")
