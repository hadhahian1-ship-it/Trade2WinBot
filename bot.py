import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# التوكن الخاص بك مباشرة لضمان التشغيل
BOT_TOKEN = "7215164495:AAHbPPPctVbDXFxvEYCrEl32AmyYRLVXTe0"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك يا مدير! بوت Monaxa يعمل الآن بنجاح 🚀")

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    
    print("البوت بدأ العمل... راقب التلجرام!")
    application.run_polling()
    
