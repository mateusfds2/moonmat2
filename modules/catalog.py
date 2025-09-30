"""
Moon-Userbot Module: Group Members Cataloguer
Cataloga todos os membros de um grupo específico no Telegram
"""

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus
from utils.misc import modules_help, prefix
from utils.db import db
import asyncio
import json
from datetime import datetime

# ID do grupo alvo
TARGET_GROUP_ID = -1002993843722


@Client.on_message(filters.command("catalog", prefix) & filters.me)
async def catalog_members(client: Client, message: Message):
    """Cataloga todos os membros do grupo especificado"""
    
    await message.edit("🔍 <b>Iniciando catalogação de membros...</b>")
    
    try:
        # Verifica se o grupo existe e se temos acesso
        chat = await client.get_chat(TARGET_GROUP_ID)
        
        await message.edit(
            f"📊 <b>Catalogando membros do grupo:</b>\n"
            f"<b>Nome:</b> {chat.title}\n"
            f"<b>ID:</b> <code>{TARGET_GROUP_ID}</code>\n\n"
            f"⏳ <i>Por favor, aguarde...</i>"
        )
        
        members_data = []
        total_count = 0
        
        # Itera sobre todos os membros do grupo
        async for member in client.get_chat_members(TARGET_GROUP_ID):
            total_count += 1
            
            # Coleta informações do membro
            user = member.user
            member_info = {
                "user_id": user.id,
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "username": user.username or None,
                "is_bot": user.is_bot,
                "is_premium": user.is_premium or False,
                "status": member.status.name,
                "joined_date": member.joined_date.isoformat() if member.joined_date else None,
                "custom_title": member.custom_title or None,
                "is_deleted": user.is_deleted or False,
                "phone_number": user.phone_number or None,
            }
            
            # Adiciona informações de admin/moderador se aplicável
            if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                member_info["privileges"] = {
                    "can_manage_chat": member.privileges.can_manage_chat if member.privileges else False,
                    "can_delete_messages": member.privileges.can_delete_messages if member.privileges else False,
                    "can_manage_video_chats": member.privileges.can_manage_video_chats if member.privileges else False,
                    "can_restrict_members": member.privileges.can_restrict_members if member.privileges else False,
                    "can_promote_members": member.privileges.can_promote_members if member.privileges else False,
                    "can_change_info": member.privileges.can_change_info if member.privileges else False,
                    "can_invite_users": member.privileges.can_invite_users if member.privileges else False,
                    "can_pin_messages": member.privileges.can_pin_messages if member.privileges else False,
                }
            
            members_data.append(member_info)
            
            # Atualiza o status a cada 50 membros
            if total_count % 50 == 0:
                await message.edit(
                    f"📊 <b>Catalogando membros...</b>\n"
                    f"<b>Grupo:</b> {chat.title}\n"
                    f"<b>Progresso:</b> {total_count} membros processados\n"
                    f"⏳ <i>Aguarde...</i>"
                )
        
        # Salva os dados no banco de dados
        catalog_data = {
            "group_id": TARGET_GROUP_ID,
            "group_title": chat.title,
            "group_username": chat.username,
            "total_members": total_count,
            "catalog_date": datetime.now().isoformat(),
            "members": members_data
        }
        
        db.set("group.catalog", f"group_{TARGET_GROUP_ID}", catalog_data)
        
        # Gera estatísticas
        bots_count = sum(1 for m in members_data if m["is_bot"])
        premium_count = sum(1 for m in members_data if m["is_premium"])
        admins_count = sum(1 for m in members_data if m["status"] in ["ADMINISTRATOR", "OWNER"])
        deleted_count = sum(1 for m in members_data if m["is_deleted"])
        
        # Mensagem final com resumo
        summary = (
            f"✅ <b>Catalogação concluída!</b>\n\n"
            f"📊 <b>Resumo:</b>\n"
            f"<b>Grupo:</b> {chat.title}\n"
            f"<b>Total de membros:</b> {total_count}\n"
            f"<b>👤 Usuários:</b> {total_count - bots_count}\n"
            f"<b>🤖 Bots:</b> {bots_count}\n"
            f"<b>⭐ Premium:</b> {premium_count}\n"
            f"<b>👑 Admins/Owner:</b> {admins_count}\n"
            f"<b>🗑️ Deletados:</b> {deleted_count}\n\n"
            f"💾 <i>Dados salvos no banco de dados</i>\n"
            f"Use <code>{prefix}cataloginfo</code> para ver informações detalhadas"
        )
        
        await message.edit(summary)
        
    except Exception as e:
        await message.edit(f"❌ <b>Erro ao catalogar membros:</b>\n<code>{str(e)}</code>")


@Client.on_message(filters.command("cataloginfo", prefix) & filters.me)
async def catalog_info(client: Client, message: Message):
    """Mostra informações do último catálogo salvo"""
    
    catalog_data = db.get("group.catalog", f"group_{TARGET_GROUP_ID}")
    
    if not catalog_data:
        return await message.edit(
            f"❌ <b>Nenhum catálogo encontrado</b>\n\n"
            f"Use <code>{prefix}catalog</code> para criar um novo catálogo"
        )
    
    total = catalog_data["total_members"]
    members = catalog_data["members"]
    
    bots = sum(1 for m in members if m["is_bot"])
    premium = sum(1 for m in members if m["is_premium"])
    admins = sum(1 for m in members if m["status"] in ["ADMINISTRATOR", "OWNER"])
    
    response = (
        f"📊 <b>Informações do Catálogo</b>\n\n"
        f"<b>Grupo:</b> {catalog_data['group_title']}\n"
        f"<b>ID:</b> <code>{catalog_data['group_id']}</code>\n"
        f"<b>Data:</b> {catalog_data['catalog_date'][:19]}\n\n"
        f"<b>👥 Total:</b> {total}\n"
        f"<b>👤 Usuários:</b> {total - bots}\n"
        f"<b>🤖 Bots:</b> {bots}\n"
        f"<b>⭐ Premium:</b> {premium}\n"
        f"<b>👑 Admins:</b> {admins}\n\n"
        f"💾 <code>{prefix}exportcat</code> - Exportar dados\n"
        f"🔍 <code>{prefix}searchcat [termo]</code> - Buscar membro"
    )
    
    await message.edit(response)


@Client.on_message(filters.command("exportcat", prefix) & filters.me)
async def export_catalog(client: Client, message: Message):
    """Exporta o catálogo em formato JSON"""
    
    catalog_data = db.get("group.catalog", f"group_{TARGET_GROUP_ID}")
    
    if not catalog_data:
        return await message.edit(f"❌ <b>Nenhum catálogo encontrado</b>")
    
    # Cria arquivo JSON
    filename = f"catalog_{TARGET_GROUP_ID}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, ensure_ascii=False, indent=2)
    
    await message.edit("📤 <b>Enviando arquivo...</b>")
    
    try:
        await client.send_document(
            message.chat.id,
            filename,
            caption=f"📊 <b>Catálogo do grupo</b>\n<b>Total:</b> {catalog_data['total_members']} membros"
        )
        await message.delete()
    except Exception as e:
        await message.edit(f"❌ <b>Erro ao enviar arquivo:</b>\n<code>{str(e)}</code>")
    finally:
        # Remove o arquivo temporário
        import os
        if os.path.exists(filename):
            os.remove(filename)


@Client.on_message(filters.command("searchcat", prefix) & filters.me)
async def search_catalog(client: Client, message: Message):
    """Busca membros no catálogo por nome ou username"""
    
    if len(message.command) < 2:
        return await message.edit(
            f"ℹ️ <b>Uso:</b> <code>{prefix}searchcat [nome/username]</code>"
        )
    
    catalog_data = db.get("group.catalog", f"group_{TARGET_GROUP_ID}")
    
    if not catalog_data:
        return await message.edit(f"❌ <b>Nenhum catálogo encontrado</b>")
    
    search_term = " ".join(message.command[1:]).lower()
    results = []
    
    for member in catalog_data["members"]:
        # Busca por nome, sobrenome ou username
        full_name = f"{member['first_name']} {member['last_name']}".lower()
        username = (member['username'] or "").lower()
        
        if search_term in full_name or search_term in username:
            results.append(member)
    
    if not results:
        return await message.edit(f"❌ <b>Nenhum membro encontrado com:</b> <code>{search_term}</code>")
    
    # Limita a 20 resultados
    results = results[:20]
    
    response = f"🔍 <b>Resultados para:</b> <code>{search_term}</code>\n\n"
    
    for i, member in enumerate(results, 1):
        name = f"{member['first_name']} {member['last_name']}".strip()
        username_str = f"@{member['username']}" if member['username'] else "Sem username"
        status_emoji = "👑" if member['status'] == "OWNER" else "🛡️" if member['status'] == "ADMINISTRATOR" else "👤"
        premium = "⭐" if member['is_premium'] else ""
        bot = "🤖" if member['is_bot'] else ""
        
        response += (
            f"{i}. {status_emoji} <b>{name}</b> {premium}{bot}\n"
            f"   {username_str} | ID: <code>{member['user_id']}</code>\n\n"
        )
    
    if len(catalog_data["members"]) > 20:
        response += f"<i>Mostrando 20 de {len(results)} resultados</i>"
    
    await message.edit(response)


modules_help["catalog"] = {
    "catalog": "Cataloga todos os membros do grupo configurado",
    "cataloginfo": "Mostra informações do último catálogo",
    "exportcat": "Exporta o catálogo em formato JSON",
    "searchcat [termo]": "Busca membros no catálogo por nome ou username",
}
