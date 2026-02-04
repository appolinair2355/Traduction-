# main.py
import asyncio
import logging
import sys
import time
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus, ParseMode  # AJOUTER ParseMode
from deep_translator import GoogleTranslator
from config import config
from datetime import datetime

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Stockage des données
message_mapping = {}
message_content_cache = {}
stats = {
    'total_translated': 0,
    'total_edited': 0,
    'errors': 0,
    'start_time': datetime.now(),
    'last_message_time': None,
    'source_connected': False,
    'target_connected': False,
    'recent_messages': []
}

notification_cache = {
    'source_notified': False,
    'target_notified': False
}

translator = GoogleTranslator(source='auto', target=config.TARGET_LANGUAGE)

app = Client(
    "translation_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    in_memory=True
)

def translate_text(text: str) -> str:
    if not text or not text.strip():
        return text
    try:
        return translator.translate(text)
    except Exception as e:
        logger.error(f"Erreur de traduction: {e}")
        stats['errors'] += 1
        return text

def format_gambling_message(text: str) -> str:
    if not text:
        return text
        
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        if not line.strip():
            formatted_lines.append('')
            continue
            
        translated_line = translate_text(line)
        
        replacements = {
            'игрок': 'Joueur',
            'выигрыш': 'GAIN',
            'проигрыш': 'PERTE',
            'проигрышь': 'PERTE',
            'Догон': 'Suite',
            'игры': 'parties',
            'игра': 'partie'
        }
        
        for rus, fr in replacements.items():
            translated_line = translated_line.replace(rus, fr)
            
        formatted_lines.append(translated_line)
    
    return '\n'.join(formatted_lines)

def is_gambling_format(text: str) -> bool:
    if not text:
        return False
    indicators = ['♠️', '♥️', '♦️', '♣️', '₽', 'игрок', 'выигрыш', 'проигрыш', 'проигрышь', 'Догон']
    return any(ind in text for ind in indicators)

def get_message_signature(text: str, caption: str = None) -> str:
    return f"{text or ''}|{caption or ''}"

async def notify_admin(client: Client, message: str):
    """Envoie une notification à l'admin avec le bon ParseMode."""
    try:
        await client.send_message(
            chat_id=config.ADMIN_ID,
            text=message,
            parse_mode=ParseMode.MARKDOWN  # CORRECTION ICI
        )
        logger.info(f"Notification envoyée à l'admin: {config.ADMIN_ID}")
    except Exception as e:
        logger.error(f"Impossible de notifier l'admin {config.ADMIN_ID}: {e}")

# ==================== COMMANDES ====================

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    is_admin = message.from_user.id == config.ADMIN_ID
    
    welcome_text = f"""
🤖 **Bot de Traduction Automatique**

Bienvenue {message.from_user.mention} !

Je traduis automatiquement les messages du canal source vers le canal cible.

📋 **Commandes disponibles :**

🔹 `/start` - Affiche ce menu
🔹 `/status` - Voir l'état du bot et la connexion aux canaux
🔹 `/stats` - Voir les statistiques de traduction
🔹 `/test` - Tester la connexion et envoyer un message test
🔹 `/last` - Voir les 5 derniers messages traités
🔹 `/check` - Vérifier si les canaux sont accessibles
🔹 `/ping` - Vérifier que le bot est en ligne
🔹 `/info` - Informations sur la configuration
🔹 `/help` - Aide détaillée

{'🔹 `/reset` - Réinitialiser les statistiques *(admin)*' if is_admin else ''}

⚙️ **Fonctionnement :**
• **Canal Source** : `{config.SOURCE_CHANNEL_ID}`
• **Canal Cible** : `{config.TARGET_CHANNEL_ID}`
• Auto-détection des éditions
• Pas de doublons garanti
    """
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistiques", callback_data="stats"),
         InlineKeyboardButton("🔍 Status", callback_data="status")],
        [InlineKeyboardButton("🧪 Test", callback_data="test"),
         InlineKeyboardButton("❓ Aide", callback_data="help")]
    ])
    
    await message.reply(welcome_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    help_text = """
📚 **AIDE DU BOT DE TRADUCTION**

**Comment ça marche ?**
1. Ajoute le bot aux deux canaux (source et cible)
2. Le bot détecte automatiquement les messages
3. Il traduit et envoie dans le canal cible
4. Si un message est édité, il met à jour la traduction

**Gestion des éditions :**
- Le bot garde une trace de chaque message
- Quand un message est modifié dans le canal source
- Il modifie automatiquement la traduction correspondante
- Pas de message en double !

**Format spécial Casino :**
Le bot détecte automatiquement les messages de jeu et traduit :
- `игрок` → **Joueur**
- `выигрыш` → **GAIN**
- `проигрыш` → **PERTE**
- `Догон` → **Suite**

**Problèmes courants :**
• Si le bot ne traduit pas → Vérifiez `/check`
• Si les éditions ne fonctionnent pas → Vérifiez les permissions d'édition
• Pour réinitialiser → `/reset` (admin uniquement)
    """
    await message.reply(help_text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("status") & filters.private)
async def status_command(client: Client, message: Message):
    uptime = datetime.now() - stats['start_time']
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    try:
        await client.get_chat(config.SOURCE_CHANNEL_ID)
        source_status = "🟢 Connecté"
        stats['source_connected'] = True
    except Exception as e:
        source_status = f"🔴 Erreur: {str(e)[:30]}"
        stats['source_connected'] = False
    
    try:
        await client.get_chat(config.TARGET_CHANNEL_ID)
        target_status = "🟢 Connecté"
        stats['target_connected'] = True
    except Exception as e:
        target_status = f"🔴 Erreur: {str(e)[:30]}"
        stats['target_connected'] = False
    
    status_text = f"""
📊 **ÉTAT DU BOT**

🟢 **Bot :** En ligne
⏱ **Uptime :** {hours}h {minutes}m {seconds}s

📡 **Canaux :**
{source_status} **Source :** `{config.SOURCE_CHANNEL_ID}`
{target_status} **Cible :** `{config.TARGET_CHANNEL_ID}`

📨 **Activité :**
• Dernier message : {stats['last_message_time'].strftime('%H:%M:%S') if stats['last_message_time'] else 'Aucun'}
• Messages trackés : {len(message_mapping)}
    """
    
    await message.reply(status_text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    uptime = datetime.now() - stats['start_time']
    total_ops = stats['total_translated'] + stats['total_edited'] + stats['errors']
    success_rate = ((stats['total_translated'] / total_ops * 100) if total_ops > 0 else 100)
    
    stats_text = f"""
📈 **STATISTIQUES**

✅ **Traduits :** `{stats['total_translated']}`
📝 **Edités :** `{stats['total_edited']}`
❌ **Erreurs :** `{stats['errors']}`
📊 **Succès :** `{success_rate:.1f}%`

⏱ **Uptime :** `{str(uptime).split('.')[0]}`
🔄 **Trackés :** `{len(message_mapping)}`
    """
    
    await message.reply(stats_text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("test") & filters.private)
async def test_command(client: Client, message: Message):
    status_msg = await message.reply("🧪 **Test en cours...**")
    
    results = []
    all_ok = True
    
    # Test canal source
    try:
        chat = await client.get_chat(config.SOURCE_CHANNEL_ID)
        results.append(f"✅ Source : {chat.title}")
        stats['source_connected'] = True
    except Exception as e:
        results.append(f"❌ Source : {str(e)}")
        all_ok = False
    
    # Test canal cible
    try:
        chat = await client.get_chat(config.TARGET_CHANNEL_ID)
        results.append(f"✅ Cible : {chat.title}")
        stats['target_connected'] = True
    except Exception as e:
        results.append(f"❌ Cible : {str(e)}")
        all_ok = False
    
    if all_ok:
        try:
            test_msg = await client.send_message(
                config.TARGET_CHANNEL_ID,
                "🧪 **Test**\n✅ Fonctionnel !"
            )
            results.append(f"✅ Envoi OK (ID: {test_msg.id})")
            
            await asyncio.sleep(1)
            await client.edit_message_text(
                config.TARGET_CHANNEL_ID,
                test_msg.id,
                "🧫 **Test**\n✅ Envoi OK\n✅ Édition OK"
            )
            results.append("✅ Édition OK")
            
            await asyncio.sleep(2)
            await test_msg.delete()
            results.append("🗑 Nettoyé")
        except Exception as e:
            results.append(f"❌ Test échoué : {str(e)}")
    
    await status_msg.edit_text("\n".join(results), parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("last") & filters.private)
async def last_command(client: Client, message: Message):
    if not stats['recent_messages']:
        await message.reply("📭 Aucun message traité.")
        return
    
    text = "📨 **DERNIERS MESSAGES**\n\n"
    
    for i, msg in enumerate(reversed(stats['recent_messages'][-5:]), 1):
        preview = msg['content'][:30] + "..." if len(msg['content']) > 30 else msg['content']
        status_icon = "✅" if msg['translated'] else "❌"
        text += f"{i}. **ID {msg['id']}** - {msg['time']}\n   {preview}\n   {status_icon}\n\n"
    
    await message.reply(text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("check") & filters.private)
async def check_command(client: Client, message: Message):
    check_msg = await message.reply("🔍 **Vérification...**")
    
    report = ["📋 **RAPPORT**\n"]
    
    # Vérification canal source
    report.append("📥 **SOURCE**")
    try:
        chat = await client.get_chat(config.SOURCE_CHANNEL_ID)
        report.append(f"• Nom : {chat.title}")
        member = await client.get_chat_member(config.SOURCE_CHANNEL_ID, "me")
        report.append(f"• Statut : {member.status.value}")
        report.append("• ✅ OK")
        stats['source_connected'] = True
    except Exception as e:
        report.append(f"• ❌ {str(e)}")
        stats['source_connected'] = False
    
    report.append("")
    
    # Vérification canal cible
    report.append("📤 **CIBLE**")
    try:
        chat = await client.get_chat(config.TARGET_CHANNEL_ID)
        report.append(f"• Nom : {chat.title}")
        member = await client.get_chat_member(config.TARGET_CHANNEL_ID, "me")
        report.append(f"• Statut : {member.status.value}")
        
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            privs = member.privileges
            report.append(f"• Post: {'✅' if privs.can_post_messages else '❌'}")
            report.append(f"• Edit: {'✅' if privs.can_edit_messages else '❌'}")
        stats['target_connected'] = True
    except Exception as e:
        report.append(f"• ❌ {str(e)}")
        stats['target_connected'] = False
    
    await check_msg.edit_text("\n".join(report), parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("ping") & filters.private)
async def ping_command(client: Client, message: Message):
    start = time.time()
    msg = await message.reply("🏓 Ping...")
    end = time.time()
    latency = (end - start) * 1000
    
    await msg.edit_text(f"🏓 Pong! `{latency:.1f}ms`")

@app.on_message(filters.command("reset") & filters.private)
async def reset_command(client: Client, message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.reply("⛔ **Admin uniquement**")
        return
    
    stats['total_translated'] = 0
    stats['total_edited'] = 0
    stats['errors'] = 0
    stats['start_time'] = datetime.now()
    message_mapping.clear()
    message_content_cache.clear()
    
    await message.reply("🗑 **Réinitialisé !**", parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("info") & filters.private)
async def info_command(client: Client, message: Message):
    is_admin = message.from_user.id == config.ADMIN_ID
    
    info_text = f"""
⚙️ **CONFIG**

🤖 **Bot :** @{(await client.get_me()).username}
👤 **Votre ID :** `{message.from_user.id}`
{'👑 **Admin**' if is_admin else ''}

📡 **Canaux :**
• Source : `{config.SOURCE_CHANNEL_ID}`
• Cible : `{config.TARGET_CHANNEL_ID}`

🔧 **Mode :** `{'Render' if config.RENDER_DEPLOYMENT else 'Local'}`
💾 **Trackés :** `{len(message_mapping)}`
    """
    
    await message.reply(info_text, parse_mode=ParseMode.MARKDOWN)

# ==================== GESTION CANAUX ====================

@app.on_chat_member_updated()
async def handle_chat_member_update(client: Client, update):
    """Détecte quand le bot est ajouté à un canal."""
    if not update.new_chat_member:
        return
    
    new_member = update.new_chat_member
    me = await client.get_me()
    
    if new_member.user.id != me.id:
        return
    
    chat = update.chat
    chat_id = chat.id
    
    if chat_id == config.SOURCE_CHANNEL_ID:
        stats['source_connected'] = True
        
        if not notification_cache['source_notified']:
            notif_text = f"""
🎯 **BOT PRÊT !**

✅ **Ajouté au canal SOURCE**

📋 **Infos :**
• Nom : {chat.title}
• ID : `{chat_id}`

🔄 En attente de messages...
            """
            await notify_admin(client, notif_text)
            notification_cache['source_notified'] = True
            
    elif chat_id == config.TARGET_CHANNEL_ID:
        stats['target_connected'] = True
        
        if not notification_cache['target_notified']:
            notif_text = f"""
🎯 **BOT CONFIGURÉ !**

✅ **Ajouté au canal CIBLE**

📋 **Infos :**
• Nom : {chat.title}
• ID : `{chat_id}`

✉️ Prêt à envoyer les traductions !
            """
            await notify_admin(client, notif_text)
            notification_cache['target_notified'] = True

# ==================== TRADUCTION ====================

@app.on_message(filters.chat(config.SOURCE_CHANNEL_ID) & (filters.text | filters.media))
async def handle_source_message(client: Client, message: Message):
    """Traite les messages du canal source."""
    try:
        source_id = message.id
        text = message.text or message.caption
        
        logger.info(f"Message reçu : {source_id}")
        stats['last_message_time'] = datetime.now()
        
        if not text and not message.media:
            return
        
        # Traduction
        if text:
            translated_text = format_gambling_message(text) if is_gambling_format(text) else translate_text(text)
        else:
            translated_text = None
        
        # Envoi
        if message.text:
            sent = await client.send_message(
                config.TARGET_CHANNEL_ID,
                translated_text or "..."
            )
        elif message.media:
            sent = await message.copy(
                config.TARGET_CHANNEL_ID,
                caption=translated_text
            )
        
        # Stockage
        message_mapping[source_id] = sent.id
        message_content_cache[source_id] = get_message_signature(text, message.caption)
        
        stats['total_translated'] += 1
        stats['recent_messages'].append({
            'id': source_id,
            'content': text or "[Média]",
            'time': datetime.now().strftime('%H:%M:%S'),
            'translated': True
        })
        
        if len(stats['recent_messages']) > 10:
            stats['recent_messages'].pop(0)
            
        logger.info(f"Traduit : {source_id} -> {sent.id}")
        
        # Première traduction notification
        if stats['total_translated'] == 1:
            await notify_admin(
                client,
                f"🎉 **Première traduction !**\n\nSource : `{source_id}`\nCible : `{sent.id}`\n\n✅ Le bot fonctionne !"
            )
        
    except Exception as e:
        logger.error(f"Erreur traduction : {e}")
        stats['errors'] += 1

@app.on_edited_message(filters.chat(config.SOURCE_CHANNEL_ID))
async def handle_edited_source_message(client: Client, message: Message):
    """Gère les messages édités."""
    try:
        source_id = message.id
        
        if source_id not in message_mapping:
            logger.warning(f"Message édité inconnu : {source_id}")
            await handle_source_message(client, message)
            return
        
        target_id = message_mapping[source_id]
        new_text = message.text or message.caption
        
        new_sig = get_message_signature(new_text, message.caption)
        if message_content_cache.get(source_id) == new_sig:
            return
        
        logger.info(f"Édition détectée : {source_id}")
        
        if new_text:
            translated = format_gambling_message(new_text) if is_gambling_format(new_text) else translate_text(new_text)
        else:
            translated = None
        
        if message.text:
            await client.edit_message_text(config.TARGET_CHANNEL_ID, target_id, translated)
        elif message.caption:
            await client.edit_message_caption(config.TARGET_CHANNEL_ID, target_id, caption=translated)
        
        message_content_cache[source_id] = new_sig
        stats['total_edited'] += 1
        
        logger.info(f"Modifié : {target_id}")
        
    except Exception as e:
        logger.error(f"Erreur édition : {e}")
        stats['errors'] += 1

# ==================== CALLBACKS ====================

@app.on_callback_query()
async def handle_callbacks(client: Client, callback_query):
    data = callback_query.data
    
    if data == "stats":
        await stats_command(client, callback_query.message)
    elif data == "status":
        await status_command(client, callback_query.message)
    elif data == "test":
        await test_command(client, callback_query.message)
    elif data == "help":
        await help_command(client, callback_query.message)
    
    await callback_query.answer()

# ==================== WEB SERVER ====================

async def health_check(request):
    return web.Response(text="Bot OK", status=200)

async def start_web_server():
    web_app = web.Application()
    web_app.router.add_get('/', health_check)
    web_app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, config.HOST, config.PORT)
    await site.start()
    logger.info(f"Serveur web port {config.PORT}")

# ==================== MAIN ====================

async def main():
    logger.info("Démarrage...")
    
    if config.RENDER_DEPLOYMENT:
        await start_web_server()
    
    await app.start()
    
    me = await app.get_me()
    logger.info(f"Bot @{me.username} démarré!")
    
    # Notification démarrage
    startup_msg = f"""
🚀 **BOT DÉMARRÉ !**

🤖 **@{me.username}** en ligne !

📋 **Config :**
• Source : `{config.SOURCE_CHANNEL_ID}`
• Cible : `{config.TARGET_CHANNEL_ID}`
• Admin : `{config.ADMIN_ID}`

⏳ En attente des canaux...
    """
    
    try:
        await notify_admin(app, startup_msg)
    except Exception as e:
        logger.error(f"Erreur notification démarrage: {e}")
    
    # Vérification initiale
    try:
        await app.get_chat(config.SOURCE_CHANNEL_ID)
        stats['source_connected'] = True
        logger.info("Source accessible")
    except Exception as e:
        logger.warning(f"Source non accessible: {e}")
    
    try:
        await app.get_chat(config.TARGET_CHANNEL_ID)
        stats['target_connected'] = True
        logger.info("Cible accessible")
    except Exception as e:
        logger.warning(f"Cible non accessible: {e}")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêt...")
    except Exception as e:
        logger.error(f"Fatal : {e}")
        sys.exit(1)
