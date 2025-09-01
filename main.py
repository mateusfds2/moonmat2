import os
import logging
import json
import asyncio
import tempfile
import traceback
import requests

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

SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_PATH != os.getcwd():
    os.chdir(SCRIPT_PATH)

# Logger básico
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ----------------------------
# Função para carregar módulos faltantes
# ----------------------------
def load_missing_modules():
    all_modules = db.get("custom.modules", "allModules", [])
    if not all_modules:
        return

    custom_modules_path = f"{SCRIPT_PATH}/modules/custom_modules"
    os.makedirs(custom_modules_path, exist_ok=True)

    try:
        f = requests.get(
            "https://raw.githubusercontent.com/The-MoonTg-project/custom_modules/main/full.txt"
        ).text
    except Exception:
        logging.error("Failed to fetch custom modules list")
        return
    modules_dict = {
        line.split("/")[-1].split()[0]: line.strip() for line in f.splitlines()
    }

    for module_name in all_modules:
        module_path = f"{custom_modules_path}/{module_name}.py"
        if not os.path.exists(module_path) and module_name in modules_dict:
            url = f"https://raw.githubusercontent.com/The-MoonTg-project/custom_modules/main/{modules_dict[module_name]}.py"
            resp = requests.get(url)
            if resp.ok:
                with open(module_path, "wb") as f:
                    f.write(resp.content)
                logging.info("Loaded missing module: %s", module_name)
            else:
                logging.warning("Failed to load module: %s", module_name)

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
# MongoDB
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
# Webhook
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
                form_data.add_field("json_data", json.dumps(data, ensure_ascii=False), content_type="application/json")

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

        if mongo_collection:
            mongo_collection.insert_one(data.copy())
            logging.info(f"[MONGODB] Mensagem salva: {data}")

        media_path = None
        if message.media:
            temp_dir = tempfile.gettempdir()
            media_path = await message.download(file_name=os.path.join(temp_dir, f"{message.cha_
