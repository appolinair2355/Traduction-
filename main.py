# main.py
import asyncio
import logging
import sys
from aiohttp import web
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CommandHandler, CallbackQueryHandler, ContextTypes
from deep_translator import GoogleTranslator
from config import config
from datetime import datetime

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Stockage
message_map = {}  # source_message_id -> target_message_id
message_text_cache = {}  # source_message_id -> text_hash
stats = {
    'translated': 0,
    'edited': 0,
    'errors': 0,
    'start_time': datetime.now(),
    'last_msg': None
}

translator = GoogleTranslator(source='auto', target='fr')

def translate(text: str) -> str:
    """Traduit le texte."""
    if not text:
        return text
    try:
        return translator.translate(text)
    except Exception as e:
        logger.error(f"Erreur traduction: {e}")
        return text

def format_casino(text: str) -> str:
    """Formate les messages de casino."""
    lines = text.split('\n')
    result = []
    for line in lines:
        if not line.strip():
            result.append('')
            continue
        tr = translate(line)
        # Corrections spécifiques casino
        tr = tr.replace('игрок', 'Joueur').replace('выигрыш', 'GAIN')
        tr = tr.replace('проигрыш', 'PERTE').replace('проигрышь', 'PERTE')
        tr = tr.replace('Догон', 'Suite').replace('игры', 'parties')
        result.append(tr)
    return '\n'.join(result

def is_casino(text: str) -> bool:
    """Détecte format casino."""
    if not text:
        return False
    signs = ['♠️', '♥️', '♦️', '♣️', '₽', 'игрок', 'выигрыш', 'проигрыш']
    return any(s in text for s in signs)

def get_hash(text: str) -> str:
    """Crée un hash simple du texte."""
    return str(hash(text)) if text else ""

# ==================== COMMANDES ====================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start."""
    user = update.effective_user
    is_admin = user.id == config.ADMIN_ID
    
    text = f"""
🤖 **Bot de Traduction Auto**

Salut {user.first_name} !

📋 **Commandes :**
/start - Ce menu
/status - État du bot
/stats - Statistiques  
/test - Tester connexion
/check - Vérifier canaux
/ping - Latence
/info - Configuration
{'/reset - Reset stats (admin)' if is_admin else ''}

⚙️ **Fonctionnement :**
• Source : `{config.SOURCE_CHANNEL_ID}`
• Cible : `{config.TARGET_CHANNEL_ID}`
• Traduction auto FR
• Édition en temps réel
"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="stats"),
         InlineKeyboardButton("🔍 Status", callback_data="status")],
        [InlineKeyboardButton("🧪 Test", callback_data="test")]
    ])
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """État du bot."""
    uptime = datetime.now() - stats['start_time']
    hours, rem = divmod(int(uptime.total_seconds()), 3600)
    mins, secs = divmod(rem, 60)
    
    text = f"""
📊 **STATUS**

🟢 Bot : En ligne
⏱ Uptime : {hours}h {mins}m {secs}s

📡 Canaux :
• Source : `{config.SOURCE_CHANNEL_ID}`
• Cible : `{config.TARGET_CHANNEL_ID}`

📨 Activité :
• Traduits : {stats['translated']}
• Édités : {stats['edited']}
• Erreurs : {stats['errors']}
• En cache : {len(message_map)}
• Dernier : {stats['last_msg'].strftime('%H:%M:%S') if stats['last_msg'] else 'Jamais'}
"""
    await update.message.reply_text(text, parse_mode='Markdown')

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistiques."""
    uptime = datetime.now() - stats['start_time']
    total = stats['translated'] + stats['edited'] + stats['errors']
    rate = (stats['translated'] / total * 100) if total > 0 else 100
    
    text = f"""
📈 **STATISTIQUES**

✅ Traduits : `{stats['translated']}`
📝 Édités : `{stats['edited']}`
❌ Erreurs : `{stats['errors']}`
📊 Taux réussite : `{rate:.1f}%`

⏱ En ligne depuis : `{str(uptime).split('.')[0]}`
"""
    await update.message.reply_text(text, parse_mode='Markdown')

async def test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test connexion."""
    msg = await update.message.reply_text("🧪 Test en cours...")
    
    results = []
    bot = context.bot
    
    # Test accès canaux
    try:
        chat = await bot.get_chat(config.SOURCE_CHANNEL_ID)
        results.append(f"✅ Source : {chat.title}")
    except Exception as e:
        results.append(f"❌ Source : {str(e)}")
    
    try:
        chat = await bot.get_chat(config.TARGET_CHANNEL_ID)
        results.append(f"✅ Cible : {chat.title}")
        
        # Test envoi
        test_msg = await bot.send_message(config.TARGET_CHANNEL_ID, "🧪 Test de connexion...")
        await asyncio.sleep(1)
        await bot.edit_message_text("🧫 Test OK - Édition fonctionne !", chat_id=config.TARGET_CHANNEL_ID, message_id=test_msg.message_id)
        await asyncio.sleep(2)
        await bot.delete_message(config.TARGET_CHANNEL_ID, test_msg.message_id)
        results.append("✅ Envoi/Édition/Suppression OK")
    except Exception as e:
        results.append(f"❌ Cible : {str(e)}")
    
    await msg.edit_text("\n".join(results), parse_mode='Markdown')

async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vérification détaillée."""
    bot = context.bot
    text = "🔍 **VÉRIFICATION CANAUX**\n\n"
    
    # Source
    text += "**📥 CANAL SOURCE**\n"
    try:
        chat = await bot.get_chat(config.SOURCE_CHANNEL_ID)
        member = await chat.get_member(bot.id)
        text += f"✅ Accessible\n"
        text += f"• Titre : {chat.title}\n"
        text += f"• Type : {chat.type}\n"
        text += f"• Mon statut : {member.status}\n"
    except Exception as e:
        text += f"❌ Erreur : {str(e)}\n"
    
    text += "\n**📤 CANAL CIBLE**\n"
    try:
        chat = await bot.get_chat(config.TARGET_CHANNEL_ID)
        member = await chat.get_member(bot.id)
        text += f"✅ Accessible\n"
        text += f"• Titre : {chat.title}\n"
        text += f"• Type : {chat.type}\n"
        text += f"• Mon statut : {member.status}\n"
        if member.status == 'administrator':
            text += f"• Peux poster : ✅\n"
            text += f"• Peux éditer : ✅\n"
    except Exception as e:
        text += f"❌ Erreur : {str(e)}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ping."""
    import time
    start = time.time()
    msg = await update.message.reply_text("🏓")
    end = time.time()
    ms = (end - start) * 1000
    await msg.edit_text(f"🏓 Pong! `{ms:.1f}ms`", parse_mode='Markdown')

async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Info configuration."""
    me = await context.bot.get_me()
    text = f"""
⚙️ **CONFIGURATION**

🤖 Bot : @{me.username}
🆔 Mon ID : `{me.id}`
👤 Ton ID : `{update.effective_user.id}`
👑 Admin : `{config.ADMIN_ID}`

📡 Canaux :
• Source : `{config.SOURCE_CHANNEL_ID}`
• Cible : `{config.TARGET_CHANNEL_ID}`

🔧 Port : `{config.PORT}`
🌐 Host : `{config.HOST}`
"""
    await update.message.reply_text(text, parse_mode='Markdown')

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset stats."""
    if update.effective_user.id != config.ADMIN_ID:
        return await update.message.reply_text("⛔ Admin uniquement")
    
    stats.update({'translated': 0, 'edited': 0, 'errors': 0, 'start_time': datetime.now()})
    message_map.clear()
    message_text_cache.clear()
    await update.message.reply_text("🗑 Statistiques réinitialisées !")

# ==================== TRADUCTION ====================

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère les nouveaux messages du canal source."""
    if not update.channel_post:
        return
    
    # Vérifie que c'est le bon canal
    if str(update.channel_post.chat_id) != config.SOURCE_CHANNEL_ID:
        return
    
    message = update.channel_post
    source_id = message.message_id
    text = message.text or message.caption
    
    logger.info(f"Nouveau message source : {source_id}")
    stats['last_msg'] = datetime.now()
    
    try:
        # Traduction
        if text:
            translated = format_casino(text) if is_casino(text) else translate(text)
        else:
            translated = None
        
        # Envoi vers cible
        bot = context.bot
        
        if message.text:
            sent = await bot.send_message(
                chat_id=config.TARGET_CHANNEL_ID,
                text=translated or "..."
            )
        elif message.photo:
            sent = await bot.send_photo(
                chat_id=config.TARGET_CHANNEL_ID,
                photo=message.photo[-1].file_id,
                caption=translated
            )
        elif message.video:
            sent = await bot.send_video(
                chat_id=config.TARGET_CHANNEL_ID,
                video=message.video.file_id,
                caption=translated
            )
        elif message.document:
            sent = await bot.send_document(
                chat_id=config.TARGET_CHANNEL_ID,
                document=message.document.file_id,
                caption=translated
            )
        else:
            # Copie simple pour autres types
            sent = await message.copy(chat_id=config.TARGET_CHANNEL_ID)
            if translated and sent.caption != translated:
                await bot.edit_message_caption(
                    chat_id=config.TARGET_CHANNEL_ID,
                    message_id=sent.message_id,
                    caption=translated
                )
        
        # Stockage
        message_map[source_id] = sent.message_id
        message_text_cache[source_id] = get_hash(text)
        
        stats['translated'] += 1
        logger.info(f"Traduit : {source_id} -> {sent.message_id}")
        
        # Notif première traduction
        if stats['translated'] == 1:
            await bot.send_message(
                config.ADMIN_ID,
                f"🎉 **Première traduction réussie !**\n\n"
                f"Source : `{source_id}`\n"
                f"Cible : `{sent.message_id}`\n\n"
                f"Le bot fonctionne parfaitement ✅",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Erreur traduction : {e}")
        stats['errors'] += 1

async def handle_edited_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère les messages édités."""
    if not update.edited_channel_post:
        return
    
    # Vérifie canal source
    if str(update.edited_channel_post.chat_id) != config.SOURCE_CHANNEL_ID:
        return
    
    message = update.edited_channel_post
    source_id = message.message_id
    new_text = message.text or message.caption
    
    logger.info(f"Message édité détecté : {source_id}")
    
    # Vérifie qu'on a déjà ce message
    if source_id not in message_map:
        logger.warning(f"Message inconnu, traitement comme nouveau : {source_id}")
        return await handle_channel_post(update, context)
    
    target_id = message_map[source_id]
    
    # Vérifie si vraiment changé
    new_hash = get_hash(new_text)
    if message_text_cache.get(source_id) == new_hash:
        logger.info(f"Pas de changement réel pour {source_id}")
        return
    
    try:
        # Traduction
        if new_text:
            translated = format_casino(new_text) if is_casino(new_text) else translate(new_text)
        else:
            translated = None
        
        bot = context.bot
        
        # Modification
        if message.text:
            await bot.edit_message_text(
                chat_id=config.TARGET_CHANNEL_ID,
                message_id=target_id,
                text=translated
            )
        else:
            await bot.edit_message_caption(
                chat_id=config.TARGET_CHANNEL_ID,
                message_id=target_id,
                caption=translated
            )
        
        message_text_cache[source_id] = new_hash
        stats['edited'] += 1
        logger.info(f"Message modifié : {target_id}")
        
    except Exception as e:
        logger.error(f"Erreur édition : {e}")
        stats['errors'] += 1

# ==================== CALLBACKS ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère les boutons."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "stats":
        await stats_cmd(update, context)
    elif query.data == "status":
        await status_cmd(update, context)
    elif query.data == "test":
        await test_cmd(update, context)

# ==================== WEB SERVER ====================

async def health(request):
    return web.Response(text="Bot OK", status=200)

async def run_web():
    app = web.Application()
    app.router.add_get('/', health)
    app.router.add_get('/health', health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.HOST, config.PORT)
    await site.start()
    logger.info(f"Web server on port {config.PORT}")

# ==================== MAIN ====================

async def main():
    # Web server pour Render
    if config.RENDER_DEPLOYMENT:
        await run_web()
    
    # Création application
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Commandes
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("test", test_cmd))
    application.add_handler(CommandHandler("check", check_cmd))
    application.add_handler(CommandHandler("ping", ping_cmd))
    application.add_handler(CommandHandler("info", info_cmd))
    application.add_handler(CommandHandler("reset", reset_cmd))
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Messages canaux
    application.add_handler(MessageHandler(filters.Chat(int(config.SOURCE_CHANNEL_ID)) & filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(MessageHandler(filters.Chat(int(config.SOURCE_CHANNEL_ID)) & filters.UpdateType.EDITED_CHANNEL_POST, handle_edited_channel_post))
    
    # Démarrage
    await application.initialize()
    await application.start()
    
    me = await application.bot.get_me()
    logger.info(f"Bot @{me.username} démarré")
    
    # Notif admin
    try:
        await application.bot.send_message(
            config.ADMIN_ID,
            f"🚀 **Bot démarré !**\n\n"
            f"@{me.username} est en ligne\n"
            f"Source : `{config.SOURCE_CHANNEL_ID}`\n"
            f"Cible : `{config.TARGET_CHANNEL_ID}`\n\n"
            f"Envoyez /start pour les commandes",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Erreur notif admin: {e}")
    
    # Run
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêt...")
    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)
