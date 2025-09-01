# main.py - Moon Userbot completo para Heroku
import os
import logging
import json
import asyncio
import tempfile
import traceback

from pyrogram import Client, idle, errors, filters
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.raw.functions.account import GetAuthorizations
from pymongo import MongoClient, errors as mongo_errors
import aiohttp

from utils import config
from utils.db import db
from utils.misc import gitrepo, userbot_version
from utils.scripts import restart
from utils.rentry import rentry_cleanup_job
from utils.module import ModuleManager

# Caminho do script
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_PATH != os.getcwd():
    os.chdir(SCRIPT_PATH)

# ----------------------------
# Logger básico e Heroku-safe
# ----------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ----------------------------
# Parâmetros do cliente Pyrogram
# ----------------------------
common_params = {
    "api_id": config.api_id,
    "api_hash": config.api_hash,
    "hide_password": True,
    "workdir": SCRIPT_PATH,
    "app_version": userbot_version,
    "device_model": f"Moon-Userbot @ {gitrepo.head.commit.hexsha[:7]}",
    "system_version": f"{os.uname().sysname} {os.uname().release}" if hasattr(os, "uname") else "",
    "sleep_threshold": 30,
    "test_mode": config.test_server,
    "parse_mode": ParseMode.HTML,
}

if config.STRINGSESSION:
    common_params["session_string"] = config.STRINGSESSION

app = Client("my_account", **common_params)

# ----------------------------
# MongoDB opcional
# ----------------------------
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB", "telegram_logs")
mongo_collection = None

if MONGO_URI:
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping')
        mongo_db = mongo_client[MONGO_DB_NAME]
        mongo_collection = mongo_db["messages"]
        logging.info("[MONGODB] Conexão estabelecida com sucesso.")
    except mongo_errors.ConnectionFailure as e:
        logging.error(f"[MONGODB] Erro ao conectar: {e}")
        mongo_collection = None

# ----------------------------
# Webhook n8n opcional
# ----------------------------
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
UPLOAD_SEMAPHORE = asyncio.Semaphore(5)

async def send_to_webhook(data, media_path=None):
    if not N8N_WEBHOOK_URL:
        return
    try:
        async with UPLOAD_SEMAPHORE:
            async with aiohttp.ClientSession() as session:
                form_data = aiohttp.FormData()
                form_data.add_field(
                    "json_data", json.dumps(data, ensure_ascii=False), content_type="application/json"
                )

                # Upload de mídia
                file_handle = None
                if media_path and os.path.exists(media_path):
                    file_handle = open(media_path, "rb")
                    form_data.add_field(
                        "file",
                        file_handle,
                        filename=os.path.basename(media_path),
                        content_type="application/octet-stream"
                    )

                async with session.post(N8N_WEBHOOK_URL, data=form_data, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status >= 400:
                        logging.error(f"[WEBHOOK] Erro {resp.status}: {await resp.text()}")
                    else:
                        logging.info(f"[WEBHOOK] Enviado com sucesso ({resp.status})")

    except asyncio.TimeoutError:
        logging.error("[WEBHOOK] Timeout ao enviar")
    except Exception as e:
        logging.error(f"[WEBHOOK] Erro: {e}\n{traceback.format_exc()}")
    finally:
        if file_handle:
            file_handle.close()
        if media_path and os.path.exists(media_path):
            try:
                os.remove(media_path)
            except OSError as e:
                logging.error(f"Erro ao remover arquivo temporário: {e}")

# ----------------------------
# Handler de mensagens
# ----------------------------
@app.on_message(filters.all)
async def log_message(client, message):
    try:
        # Ignora mensagens enviadas pelo próprio usuário
        if message.outgoing:
            return

        text_content = message.text or message.caption or ""
        from_user = message.from_user or message.forward_from

        data = {
            "chat_id": message.chat.id,
            "chat_title": getattr(message.chat, "title", getattr(message.chat, "first_name", None)),
            "message_id": message.id,
            "from_user_id": getattr(from_user, "id", None),
            "username": getattr(from_user, "username", None),
            "first_name": getattr(from_user, "first_name", None),
            "text": text_content,
            "has_media": bool(message.media),
            "media_type": str(message.media) if message.media else None,
            "date": message.date.isoformat() if message.date else None,
        }

        # Salva no MongoDB
        if mongo_collection:
            mongo_collection.insert_one(data.copy())
            logging.info(f"[MONGODB] Mensagem salva: {data}")

        # Download de mídia
        media_path = None
        if message.media:
            try:
                temp_dir = tempfile.gettempdir()
                media_path = await message.download(file_name=os.path.join(temp_dir, f"{message.chat.id}_{message.id}"))
                logging.info(f"Mídia baixada: {media_path}")
            except Exception as e:
                logging.error(f"Falha ao baixar mídia: {e}")

        # Envia para webhook sem bloquear
        asyncio.create_task(send_to_webhook(data, media_path))

    except Exception as e:
        logging.error(f"[LOGGER] Erro: {e}\n{traceback.format_exc()}")

# ----------------------------
# Função principal
# ----------------------------
async def main():
    try:
        await app.start()
    except Exception as e:
        logging.error(f"[STARTUP] Erro ao iniciar: {e}")
        raise

    # Carrega módulos
    load_missing_modules()
    module_manager = ModuleManager.get_instance()
    await module_manager.load_modules(app)

    # Sessionkiller
    if db.get("core.sessionkiller", "enabled", False):
        db.set(
            "core.sessionkiller",
            "auths_hashes",
            [auth.hash for auth in (await app.invoke(GetAuthorizations())).authorizations]
        )

    logging.info("Moon-Userbot iniciado com sucesso!")
    app.loop.create_task(rentry_cleanup_job())
    await idle()
    await app.stop()

# ----------------------------
# Inicialização
# ----------------------------
if __name__ == "__main__":
    app.run(main())
