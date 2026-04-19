from telegram import Update
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config
from models.user_quota import grant_unlimited, ban_user, reset_usage


async def unlimited_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/unlimited <user_id> — выдать/забрать безлимит"""
    if update.effective_user.id not in config.ADMINS:  # твой список админов
        return

    if not context.args:
        await update.message.reply_text("Используй: `/unlimited 8039643413`")
        return

    try:
        target_id = int(context.args[0])
        grant_unlimited(target_id, grant=True)
        await update.message.reply_text(f"✅ Безлимит выдан user_{target_id}")
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id")


async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ban <user_id> — забанить пользователя (привет, Вася)"""
    if update.effective_user.id not in config.ADMINS:
        return

    if not context.args:
        await update.message.reply_text("Используй: `/ban 123456789`")
        return

    try:
        target_id = int(context.args[0])
        ban_user(target_id, ban=True)
        await update.message.reply_text(f"🔒 user_{target_id} забанен. Ветчина в безопасности.")
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id")


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset <user_id> — сбросить счётчик (для тестов)"""
    if update.effective_user.id not in config.ADMINS:
        return

    if not context.args:
        await update.message.reply_text("Используй: `/reset 123456789`")
        return

    try:
        target_id = int(context.args[0])
        reset_usage(target_id)
        await update.message.reply_text(f"🔄 Счётчик сброшен для user_{target_id}")
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id")