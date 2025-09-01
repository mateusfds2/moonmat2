#  Moon-Userbot - telegram userbot
#  Copyright (C) 2020-present Moon Userbot Organization
#
#  Licensed under the GNU General Public License v3.0

import os
import logging
import sqlite3
import platform
import subprocess
import tempfile
import traceback
import asyncio

from pyrogram import Client, idle, errors, filters
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.raw.functions.account import GetAuthorizations, DeleteAccount
import requests
from utils import config
from utils.db import db
from utils.misc import gitrepo, userbot_version
from utils.scripts import restart
from utils.rentry import rentry_cleanup_job
from utils.module import ModuleManager

import aiohttp

SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_PATH != os.getcwd():
    os.chdir(SCRIPT_PATH)

common_params = {
    "api_id": config.api_id,
    "api_hash": config.api_hash,
    "hide_password": True,
    "workdir": SCRIPT_PATH,
    "app_version": userbot_version,
    "device_model": f"Moon-Userbot @ {gitrepo.head.commit.hexsha[:7]}",
    "system_version": platform.version() + " " + platform.machine(),
    "sleep_threshold": 30,
    "test_mode": config.test_server,
    "parse_mode": ParseMode.HTML,
}

if config.STRINGSESSION:
    common_params["session_string"] = config.STRINGSESSION

app = Client("my_account", **common_params)

# --- Funções auxiliares ---

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

    modules_dict = {line.split("/")[-1].split()[0]: line.strip() for line in f.splitlines()}

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

# --- Logger para webhook e MongoDB ---

async def send_to_webhook(data: dict, media_path: str = None):
    N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
    if not N8N_WEBHOOK_URL:
        return

    try:
        form = data.copy()
        if media_path and os.path.exists(media_path):
            with open(media_path, "rb") as f:
                form["file"] = f.read()

        async with aiohttp.ClientSession() as session:
            async with session.post(N8N_WEBHOOK_URL, data=form, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    logging.info("[WEBHOOK] Mensagem enviada com sucesso")
                else:
                    logging.warning(f"[WEBHOOK] Status {resp.status}")
    except Exception as e:
        logging.error(f"[WEBHOOK ERRO] {e}\n{traceback.format_exc()}")

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

        if db.get("core.mongodb", "enabled", True):
            from utils.db import mongo_collection
            mongo_collection.insert_one(data.copy())
            logging.info(f"[MONGODB] Mensagem salva: {data}")

        media_path = None
        if message.media:
            temp_dir = tempfile.gettempdir()
            media_path = await message.download(
                file_name=os.path.join(temp_dir, f"{message.chat.id}_{message.id}")
            )
            logging.info(f"Mídia baixada: {media_path}")

        asyncio.create_task(send_to_webhook(data, media_path))

    except Exception as e:
        logging.error(f"[LOGGER] Erro: {e}\n{traceback.format_exc()}")

# --- Função principal ---

async def main():
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler("moonlogs.txt"), logging.StreamHandler()],
        level=logging.INFO,
    )

    DeleteAccount.__new__ = None

    try:
        await app.start()
    except sqlite3.OperationalError as e:
        if str(e) == "database is locked" and os.name == "posix":
            logging.warning("Session file is locked. Tentando matar processo bloqueando...")
            subprocess.run(["fuser", "-k", "my_account.session"], check=True)
            restart()
        raise
    except (errors.NotAcceptable, errors.Unauthorized) as e:
        logging.error(f"{e.__class__.__name__}: {e}\nMovendo session file para my_account.session-old")
        os.rename("./my_account.session", "./my_account.session-old")
        restart()

    load_missing_modules()
    module_manager = ModuleManager.get_instance()
    await module_manager.load_modules(app)

    if info := db.get("core.updater", "restart_info"):
        text = {"restart": "<b>Restart completed!</b>", "update": "<b>Update process completed!</b>"}[info["type"]]
        try:
            await app.edit_message_text(info["chat_id"], info["message_id"], text)
        except errors.RPCError:
            pass
        db.remove("core.updater", "restart_info")

    if db.get("core.sessionkiller", "enabled", False):
        db.set(
            "core.sessionkiller",
            "auths_hashes",
            [auth.hash for auth in (await app.invoke(GetAuthorizations())).authorizations],
        )

    logging.info("Moon-Userbot started!")

    app.loop.create_task(rentry_cleanup_job())

    await idle()
    await app.stop()

# --- Execução ---

if __name__ == "__main__":
    app.run(main())
