import os
import json
import aiohttp
import asyncio
import tempfile
import logging
import traceback
from pyrogram import Client, filters
from pymongo import MongoClient, errors

# 🔹 Configuração de logs detalhados
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(message)s"
)

# 🔹 Carregamento das configurações de ambiente
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB", "telegram_logs")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

# 🔹 Validação de variáveis essenciais
missing_vars = []
if not API_ID:
    missing_vars.append("API_ID")
if not API_HASH:
    missing_vars.append("API_HASH")
if not SESSION_STRING:
    missing_vars.append("SESSION_STRING")

if missing_vars:
    logging.error(f"[ERRO CRÍTICO] As seguintes variáveis de ambiente são obrigatórias, mas não foram encontradas: {', '.join(missing_vars)}")
    exit(1)

try:
    API_ID = int(API_ID)
except (ValueError, TypeError):
    logging.error(f"[ERRO CRÍTICO] API_ID ('{API_ID}') não é um número inteiro válido.")
    exit(1)

# 🔹 Conexão com MongoDB
mongo_client = None
db = None
collection = None
if MONGO_URI:
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping')
        db = mongo_client[MONGO_DB_NAME]
        collection = db["messages"]
        logging.info("[MONGODB] Conexão estabelecida com sucesso.")
    except errors.ConnectionFailure as e:
        logging.error(f"[MONGODB ERRO] Falha ao conectar com MongoDB: {e}")
        mongo_client = db = collection = None
    except Exception as e:
        logging.error(f"[MONGODB ERRO INESPERADO] {e}")
        mongo_client = db = collection = None
else:
    logging.warning("[MONGODB] MONGO_URI não definida. O logger não salvará mensagens no banco.")

# 🔹 Limite de uploads simultâneos
UPLOAD_SEMAPHORE = asyncio.Semaphore(5)

async def send_to_webhook(data, media_path=None):
    """Envia dados para o n8n via webhook, incluindo mídia se existir."""
    if not N8N_WEBHOOK_URL:
        return

    try:
        async with UPLOAD_SEMAPHORE:
            async with aiohttp.ClientSession() as session:
                form_data = aiohttp.FormData()
                form_data.add_field(
                    'json_data',
                    json.dumps(data, ensure_ascii=False),
                    content_type='application/json'
                )

                file_obj = None
                if media_path and os.path.exists(media_path):
                    file_obj = open(media_path, "rb")
                    form_data.add_field(
                        "file",
                        file_obj,
                        filename=os.path.basename(media_path),
                        content_type="application/octet-stream"
                    )

                try:
                    async with session.post(N8N_WEBHOOK_URL, data=form_data, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        if resp.status >= 400:
                            logging.error(f"[WEBHOOK] Erro ao enviar. Status: {resp.status} | Resposta: {await resp.text()}")
                        else:
                            logging.info(f"[WEBHOOK] Enviado com sucesso. Status: {resp.status}")
                finally:
                    if file_obj:
                        file_obj.close()

    except asyncio.TimeoutError:
        logging.error("[WEBHOOK ERRO] Timeout ao enviar para o n8n.")
    except Exception as e:
        logging.error(f"[WEBHOOK ERRO] {e}\n{traceback.format_exc()}")
    finally:
        if media_path and os.path.exists(media_path):
            try:
                os.remove(media_path)
            except OSError as e:
                logging.error(f"Erro ao remover arquivo de mídia temporário: {e}")

# 🔹 Inicialização do cliente Pyrogram
app = Client(
    "moon_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

@app.on_message(filters.all & ~filters.service)
async def log_message(client, message):
    try:
        if getattr(message, "outgoing", False):
            return

        text_content = getattr(message, "text", None) or getattr(message, "caption", None) or ""
        from_user = getattr(message, "from_user", None) or getattr(message, "forward_from", None)
        chat = getattr(message, "chat", None)

        chat_id = getattr(chat, "id", None)
        chat_title = getattr(chat, "title", None) or getattr(chat, "first_name", None)
        msg_id = getattr(message, "message_id", None) or getattr(message, "id", None)

        data = {
            "chat_id": chat_id,
            "chat_title": chat_title,
            "message_id": msg_id,
            "from_user_id": getattr(from_user, "id", None),
            "username": getattr(from_user, "username", None),
            "first_name": getattr(from_user, "first_name", None),
            "text": text_content,
            "has_media": bool(getattr(message, "media", None)),
            "media_type": str(getattr(message, "media", None)) if getattr(message, "media", None) else None,
            "date": getattr(message, "date", None).isoformat() if getattr(message, "date", None) else None,
        }

        # Salva no MongoDB
        if collection:
            collection.insert_one(data.copy())
            logging.info(f"[MONGODB] Mensagem salva: {data}")

        # Download da mídia em diretório temporário
        media_path = None
        if getattr(message, "media", None):
            try:
                temp_dir = tempfile.gettempdir()
                media_path = await message.download(file_name=os.path.join(temp_dir, f"{chat_id}_{msg_id}"))
                logging.info(f"Mídia baixada: {media_path}")
            except Exception as e:
                logging.error(f"Falha ao baixar mídia: {e}")

        # Envia para o webhook sem bloquear o bot
        asyncio.create_task(send_to_webhook(data, media_path))

    except Exception as e:
        logging.error(f"[LOGGER ERRO] Exceção não tratada: {e}\n{traceback.format_exc()}")

if __name__ == "__main__":
    logging.info("[START] Moon Userbot iniciando...")
    app.run()
    logging.info("[STOP] Moon Userbot finalizado.")
