import os
import logging
import asyncio
import datetime
# from keep_alive import keep_alive
# keep_alive()
import random
import time
import urllib.parse
from io import BytesIO
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMember,
    InputFile,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
import storage

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "7215164495:AAHbPPPctVbDXFxvEYCrEl32AmyYRLVXTe0"
ADMIN_GROUP_ID = int(os.environ["ADMIN_GROUP_ID"])
ADMIN_USER_ID = int(os.environ["ADMIN_USER_ID"])
REQUIRED_CHANNEL  = "@Trad_2win"
MONAXA_REG_URL    = "https://account.monaxa.com/links/go/18626"  # official T2W agency link
WEBHOOK_URL       = "https://kyc-bot-verify-hadhahian1.replit.dev/webhook"
WEBHOOK_PORT      = int(os.environ.get("PORT", 8000))

FULL_NAME, ID_PHOTO = range(2)
BROADCAST_TEXT, BROADCAST_PHOTO = range(2, 4)
USER_LOOKUP = 4

BOT_USERNAME = ""

# Cached logo path (written once on startup by fetch_admin_logo)
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "admin_logo.jpg")


async def on_startup(app) -> None:
    """Combined post_init: fetch logo + notify admin the bot is online."""
    await fetch_admin_logo(app)
    try:
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        await app.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=(
                "🚀 *النظام الآن يعمل على سيرفر محمي ومستقل*\n\n"
                "يمكنك إغلاق الهاتف والإنترنت، سأبقى متاحاً لعملائك في Monaxa "
                "على مدار الساعة. ⏰\n\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"🕐 وقت التشغيل: `{ts}`\n"
                "🟢 الحالة: *متصل* — يستقبل الرسائل\n"
                "🔗 الوضع: *Polling* — استقبال مستمر\n"
                "🔄 إعادة التشغيل التلقائي: *مفعّلة*\n"
                "📊 التقرير اليومي: *09:00 كل يوم*\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "_Trade 2 Win · Powered by Monaxa_"
            ),
            parse_mode="Markdown",
        )
        logger.info("Admin startup notification sent.")
        logger.info("Webhook set successfully at %s", WEBHOOK_URL)
    except Exception as _e:
        logger.warning(f"Could not send admin startup ping: {_e}")


async def fetch_admin_logo(app) -> None:
    """
    Download the admin's Telegram profile photo once on startup and cache it
    to disk so prize_image.py can embed it as a circular logo on certificates.
    Re-downloads if the file is older than 7 days so the logo stays fresh.
    """
    import time as _time
    os.makedirs(os.path.dirname(_LOGO_PATH), exist_ok=True)

    # Re-use cached file if it's fresh (< 7 days old)
    if os.path.exists(_LOGO_PATH):
        age_days = (_time.time() - os.path.getmtime(_LOGO_PATH)) / 86400
        if age_days < 7:
            logger.info("Admin logo cache is fresh — skipping re-download.")
            return

    try:
        photos = await app.bot.get_user_profile_photos(ADMIN_USER_ID, limit=1)
        if not photos.photos:
            logger.warning("Admin account has no profile photos — logo skipped.")
            return
        # Pick the largest available size
        largest = photos.photos[0][-1]
        file_obj = await app.bot.get_file(largest.file_id)
        await file_obj.download_to_drive(_LOGO_PATH)
        logger.info(f"Admin logo saved to {_LOGO_PATH}")
    except Exception as exc:
        logger.warning(f"Could not fetch admin logo: {exc}")


# ─────────────────────────────────────────────
#  KEYBOARDS
# ─────────────────────────────────────────────

def subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📢 اشترك في قناة @Trad_2win",
            url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}"
        )
    ]])


def kyc_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ التحقق من الهوية الآن", callback_data="start_kyc")
    ]])


def main_menu_keyboard(spins: int = 1) -> InlineKeyboardMarkup:
    if spins == -1:
        wheel_label = "🎡 عجلة الحظ — محاولات غير محدودة (مدير) ♾️"
    else:
        wheel_label = f"🎡 عجلة الحظ (المحاولات المتاحة: {spins})"
    keyboard = [
        [InlineKeyboardButton("💼 الوظائف", callback_data="menu_careers")],
        [InlineKeyboardButton("🎁 قسم العروض", callback_data="menu_offers")],
        [InlineKeyboardButton("🔄 نقل الوكالة", callback_data="menu_ib_transfer")],
        [InlineKeyboardButton("🏆 قسم المسابقات", callback_data="menu_contests")],
        [InlineKeyboardButton("🔗 روابط الدعوة", callback_data="menu_referral")],
        [InlineKeyboardButton("📊 التحليل الذكي (الذهب)", callback_data="menu_gold_ai")],
        [InlineKeyboardButton("💳 إيداع وسحب USDT", callback_data="menu_usdt")],
        [InlineKeyboardButton(wheel_label, callback_data="menu_wheel")],
        [InlineKeyboardButton("فتح حساب تحت وكالة Trade 2 Win 📈", callback_data="menu_open_account")],
        [InlineKeyboardButton("الدعم الفني لشركة Monaxa 🎧", callback_data="menu_monaxa_support")],
        [InlineKeyboardButton("لماذا التداول مع Monaxa؟ 🏆", callback_data="menu_why_monaxa")],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")
    ]])


def offers_submenu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 الكاش باك", callback_data="offer_cashback")],
        [InlineKeyboardButton("🔥 بونص 100%", callback_data="offer_bonus100")],
        [InlineKeyboardButton("🚀 بونص 50%", callback_data="offer_bonus50")],
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
    ])


def referral_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 رابط الدعوة الخاص بي", callback_data="referral_link")],
        [InlineKeyboardButton("📊 إحصائياتي", callback_data="referral_stats")],
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
    ])


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 إحصائيات البوت",       callback_data="admin_stats")],
        [InlineKeyboardButton("🏅 قائمة المتصدرين",      callback_data="admin_top_referrers")],
        [InlineKeyboardButton("🎡 إحصائيات العجلة",      callback_data="admin_wheel_stats")],
        [InlineKeyboardButton("💵 سجل الجوائز المالية",  callback_data="admin_prizes_ledger")],
        [InlineKeyboardButton("📣 إرسال منشور للكل",     callback_data="admin_broadcast_text")],
        [InlineKeyboardButton("🖼️ إرسال صورة للكل",     callback_data="admin_broadcast_photo")],
        [InlineKeyboardButton("🔍 بحث عن مستخدم",       callback_data="admin_user_lookup")],
    ])


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in [
            ChatMember.MEMBER,
            ChatMember.ADMINISTRATOR,
            ChatMember.OWNER,
        ]
    except Exception as e:
        logger.warning(f"Subscription check failed for {user_id}: {e}")
        return False


async def send_main_menu(target, user_first_name: str, user_id: int = 0, edit: bool = False):
    spins = await storage.async_get_available_spins(user_id) if user_id else 1
    text = (
        f"أهلاً {user_first_name}! 👋\n\n"
        "📋 القائمة الرئيسية — اختر ما تريد:"
    )
    kb = main_menu_keyboard(spins)
    if edit:
        await target.edit_message_text(text, reply_markup=kb)
    else:
        await target.reply_text(text, reply_markup=kb)


async def _require_approved(query) -> bool:
    user = query.from_user
    if storage.is_approved(user.id):
        return True
    if storage.is_pending(user.id):
        await query.answer(
            "⏳ طلبك لا يزال قيد المراجعة. سيتم إعلامك قريباً.", show_alert=True
        )
    else:
        await query.answer(
            "⚠️ يجب إكمال التحقق من الهوية أولاً. اضغط /start", show_alert=True
        )
    return False


def _is_admin(user_id: int) -> bool:
    return user_id == ADMIN_USER_ID


# ─────────────────────────────────────────────
#  /start — STRICT GATED WORKFLOW
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BOT_USERNAME
    if not BOT_USERNAME:
        me = await context.bot.get_me()
        BOT_USERNAME = me.username

    user = update.effective_user
    display_name = user.full_name or user.first_name or str(user.id)
    storage.register_user(user.id, display_name)
    args = context.args

    # Handle referral deep link
    if args:
        try:
            inviter_id = int(args[0])
            if storage.record_referral(user.id, inviter_id):
                logger.info(f"User {user.id} joined via referral from {inviter_id}")
                try:
                    await context.bot.send_message(
                        chat_id=inviter_id,
                        text=(
                            f"🎉 مبروك! انضم عضو جديد عن طريق رابط دعوتك.\n"
                            f"👤 المستخدم: {user.full_name}\n\n"
                            "استمر في مشاركة رابطك لزيادة فرصك في الفوز!"
                        )
                    )
                except Exception:
                    pass
        except (ValueError, TypeError):
            pass

    WELCOME = (
        "مرحباً بك يا بطل في بوت Trade 2 Win الرسمي! 🏆\n\n"
        "نحن هنا لنساعدك على النجاح في أسواق المال وتداول الذهب والعملات الرقمية "
        "مع شركائنا في Monaxa.\n\n"
        "⚠️ تنبيه: يجب أن تكون مشتركاً في قناتنا @Trad_2win لتفعيل كافة ميزات "
        "البوت والحصول على نقاطك."
    )

    # STEP 1: Check subscription
    is_subscribed = await check_subscription(user.id, context)
    if not is_subscribed:
        await update.message.reply_text(
            WELCOME + "\n\n👇 اشترك أولاً ثم اضغط /start مجدداً:",
            reply_markup=subscribe_keyboard(),
        )
        return

    # STEP 2: Check KYC
    if storage.is_approved(user.id):
        await update.message.reply_text(WELCOME)
        await send_main_menu(update.message, user.first_name, user.id)
        return

    if storage.is_pending(user.id):
        await update.message.reply_text(
            WELCOME + "\n\n⏳ طلب التحقق من هويتك قيد المراجعة حالياً.\n"
            "سيتم إعلامك فور اتخاذ القرار. شكراً على صبرك!"
        )
        return

    await update.message.reply_text(
        WELCOME + "\n\n✅ اشتراكك مؤكد! الخطوة التالية هي التحقق من هويتك (KYC) "
        "لفتح القائمة الكاملة.",
        reply_markup=kyc_prompt_keyboard(),
    )


# ─────────────────────────────────────────────
#  KYC CONVERSATION
# ─────────────────────────────────────────────

async def verify_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if storage.is_approved(user.id):
        await query.edit_message_text(
            "✅ هويتك موثقة بالفعل! اضغط /start للوصول إلى القائمة الكاملة."
        )
        return ConversationHandler.END

    if storage.is_pending(user.id):
        await query.edit_message_text("⏳ طلبك قيد المراجعة. سيتم إعلامك قريباً.")
        return ConversationHandler.END

    is_subscribed = await check_subscription(user.id, context)
    if not is_subscribed:
        await query.edit_message_text(
            f"⚠️ يجب الاشتراك في {REQUIRED_CHANNEL} أولاً.\n\nاضغط /start بعد الاشتراك.",
            reply_markup=subscribe_keyboard(),
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "📋 التحقق من الهوية (KYC)\n\n"
        "سنقوم بالتحقق من هويتك في خطوتين سريعتين.\n"
        "بعد الموافقة تُفتح لك القائمة الكاملة.\n\n"
        "📝 الخطوة 1 من 2 — يرجى إدخال اسمك الكامل:"
    )
    return FULL_NAME


async def receive_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["full_name"] = update.message.text.strip()
    await update.message.reply_text(
        "📷 الخطوة 2 من 2 — يرجى إرسال صورة واضحة لوثيقة هويتك:\n"
        "(جواز السفر / الهوية الوطنية / رخصة القيادة)"
    )
    return ID_PHOTO


async def receive_id_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not update.message.photo:
        await update.message.reply_text("⚠️ يرجى إرسال صورة واضحة لوثيقة هويتك.")
        return ID_PHOTO

    photo = update.message.photo[-1]
    full_name = context.user_data.get("full_name", "N/A")
    storage.set_pending(user.id)

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قبول", callback_data=f"accept_{user.id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user.id}"),
    ]])
    caption = (
        "🔔 طلب تحقق هوية جديد (KYC)\n\n"
        f"👤 الاسم: {user.full_name}\n"
        f"🔖 المعرف: @{user.username or 'N/A'}\n"
        f"🆔 User ID: {user.id}\n"
        f"📛 الاسم الكامل المُدخل: {full_name}"
    )

    # ── 1. Always deliver to admin DM first (guaranteed) ──────────────────
    logger.info("Forwarding KYC photo to Admin (user_id=%s, name=%s)...", user.id, user.full_name)
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_USER_ID,
            photo=photo.file_id,
            caption=caption,
            reply_markup=keyboard,
        )
        logger.info("KYC photo delivered to admin DM successfully.")
    except Exception as dm_err:
        logger.error("CRITICAL: Failed to deliver KYC to admin DM: %s", dm_err)

    # ── 2. Also forward to the admin group if reachable (bonus copy) ───────
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=photo.file_id,
            caption=caption,
            reply_markup=keyboard,
        )
        logger.info("KYC photo also delivered to admin group.")
    except Exception as group_err:
        logger.warning(
            "Admin group delivery failed (group_id=%s) — DM copy already sent. Error: %s",
            ADMIN_GROUP_ID, group_err,
        )

    await update.message.reply_text(
        "✅ شكراً! تم إرسال طلب التحقق بنجاح.\n\n"
        "⏳ سيقوم فريقنا بمراجعة وثائقك وإعلامك بالنتيجة قريباً.\n"
        "لن تحتاج للقيام بأي شيء آخر الآن."
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_kyc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("تم الإلغاء. اضغط /start للبدء من جديد.")
    return ConversationHandler.END


# ─────────────────────────────────────────────
#  ADMIN DECISION (Accept / Reject KYC)
# ─────────────────────────────────────────────

async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Allow decisions from the admin group OR the admin's personal DM
    # (DM fallback activates when the bot can't reach the group)
    allowed_chats = {ADMIN_GROUP_ID, ADMIN_USER_ID}
    if query.message.chat.id not in allowed_chats:
        await query.answer("⛔ غير مصرح لك باتخاذ هذا الإجراء.", show_alert=True)
        return

    data = query.data
    action, target_str = data.split("_", 1)
    target_user_id = int(target_str)
    admin = query.from_user
    original_caption = query.message.caption or ""

    if action == "accept":
        storage.approve_user(target_user_id)
        status_label = "✅ مقبول"
        user_msg = (
            "🎉 تهانينا! تم قبول طلب التحقق من هويتك (KYC) بنجاح.\n\n"
            "✅ هويتك موثقة الآن. اضغط /start للوصول إلى القائمة الكاملة والاستفادة "
            "من جميع مزايا المنصة."
        )
    elif action == "reject":
        storage.reject_user(target_user_id)
        status_label = "❌ مرفوض"
        user_msg = (
            "⚠️ نأسف! تم رفض طلب التحقق من هويتك (KYC).\n\n"
            "يرجى التأكد من أن وثائقك واضحة وصالحة، ثم أعد المحاولة بالضغط على /start.\n"
            "إذا احتجت مساعدة تواصل مع الدعم: @B_T2w"
        )
    else:
        return

    try:
        await context.bot.send_message(chat_id=target_user_id, text=user_msg)
    except Exception as e:
        logger.error(f"Could not notify user {target_user_id}: {e}")

    new_caption = (
        original_caption
        + f"\n\n━━━━━━━━━━━━━\n{status_label} — بواسطة {admin.full_name}"
    )
    await query.edit_message_caption(caption=new_caption, reply_markup=None)


# ─────────────────────────────────────────────
#  MAIN MENU
# ─────────────────────────────────────────────

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    await send_main_menu(query, query.from_user.first_name, query.from_user.id, edit=True)


# ─────────────────────────────────────────────
#  CAREERS
# ─────────────────────────────────────────────

async def menu_careers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    await query.edit_message_text(
        "💼 الوظائف\n\n"
        "إذا لديك خبرة في التداول والتحليل ولديك جمهورك من المتداولين، "
        "تواصل معنا للتعاون:\n\n"
        "👤 @B_T2w",
        reply_markup=back_keyboard(),
    )


# ─────────────────────────────────────────────
#  OFFERS
# ─────────────────────────────────────────────

async def menu_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    await query.edit_message_text(
        "🎁 قسم العروض\n\nاختر العرض الذي يناسبك:",
        reply_markup=offers_submenu_keyboard(),
    )


async def offer_cashback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    await query.edit_message_text(
        "💰 الكاش باك\n\n"
        "انقل حسابك تحت وكالتنا وحصل على كاش باك:\n\n"
        "🔸 1 $ لكل لوت يتم تداوله\n\n"
        "📌 ملاحظة: يتم دفع الكاش باك نهاية كل شهر.\n\n"
        "للتفاصيل والتفعيل تواصل مع الدعم:\n"
        "👤 @B_T2w",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 العودة للعروض", callback_data="menu_offers")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="menu_main")],
        ]),
    )


async def offer_bonus100(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    await query.edit_message_text(
        "🔥 بونص 100%\n\n"
        "⏳ سيتم توفير العرض قريباً.\n\n"
        "ترقبوا الإعلان في قناتنا @Trad_2win",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 العودة للعروض", callback_data="menu_offers")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="menu_main")],
        ]),
    )


async def offer_bonus50(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    await query.edit_message_text(
        "🚀 بونص Monaxa الحصري 50%\n"
        "(قابل للتداول والخسارة)\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "✅ احصل على مكافأة 50% فورية على إيداعك\n"
        "✅ البونص قابل للتداول والسحب بعد استيفاء شروط الحجم\n"
        "✅ متاح لجميع العملاء الجدد والحاليين\n"
        "✅ لا حد أقصى للمكافأة — كلما أودعت أكثر ربحت أكثر\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📌 شروط العرض:\n\n"
        "• الحد الأدنى للإيداع: 100$\n"
        "• لا يمكن سحب البونص مباشرة — يُستخدم كهامش تداول\n"
        "• يمكن سحب الأرباح الناتجة عن التداول بحرية تامة\n"
        "• العرض محدود المدة — يُطبّق على أول إيداع مؤهّل\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💡 مثال عملي:\n"
        "أودعت 1,000$ ← تحصل على 500$ بونص إضافي\n"
        "رأس مالك الفعلي في التداول: 1,500$ 🚀\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🔗 رابط التسجيل:\n"
        f"{MONAXA_REG_URL}\n\n"
        "📩 للمساعدة في تفعيل البونص: @B_T2w",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📝 سجّل الآن واحصل على البونص",
                url=MONAXA_REG_URL
            )],
            [InlineKeyboardButton("🔙 العودة للعروض", callback_data="menu_offers")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="menu_main")],
        ]),
    )


# ─────────────────────────────────────────────
#  IB TRANSFER
# ─────────────────────────────────────────────

async def menu_ib_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    await query.edit_message_text(
        "🔄 نقل الوكالة — IB Transfer\n\n"
        "ادخل حسابك على موناكسا من المتصفح وافتح سماعة الدعم،\n"
        "ثم اختر: الشراكات والتشبيك\n\n"
        "ثم اكتب الرسالة التالية للدعم:\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Hello support please move my account under IB bashair ( CID 131297 )\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ بعد النقل تستفيد من:\n"
        "• كاش باك شهري على كل لوت\n"
        "• دعم مباشر من فريق Trade 2 Win\n"
        "• عروض وحوافز حصرية\n\n"
        "📩 إذا واجهت أي مشكلة: @B_T2w",
        reply_markup=back_keyboard(),
    )


# ─────────────────────────────────────────────
#  CONTESTS
# ─────────────────────────────────────────────

async def menu_contests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    await query.edit_message_text(
        "🏆 قسم المسابقات\n\n"
        "أنشئ رابط دعوة خاص بك وكل عضو ينضم عن طريقك "
        "يمنحك فرصة حقيقية لربح جائزة مالية! 🎉\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🎯 كيف تشارك؟\n\n"
        "1️⃣ اذهب إلى قسم 🔗 روابط الدعوة من القائمة الرئيسية\n"
        "2️⃣ انسخ رابط الدعوة الخاص بك\n"
        "3️⃣ شاركه مع أصدقائك ومتابعيك\n"
        "4️⃣ كل عضو جديد يسجل عبر رابطك يُضاف إلى رصيدك\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🏅 الجوائز تُعلن دورياً في قناة @Trad_2win\n"
        "تابع القناة لا تفوّت الفرص!",
        reply_markup=back_keyboard(),
    )


# ─────────────────────────────────────────────
#  REFERRAL SYSTEM
# ─────────────────────────────────────────────

async def menu_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    user = query.from_user
    await query.edit_message_text(
        "🔗 روابط الدعوة\n\n"
        "شارك رابط الدعوة الخاص بك واحصل على مكافآت!\n"
        "كل عضو ينضم عبر رابطك يُحتسب في رصيدك.",
        reply_markup=referral_menu_keyboard(user.id),
    )


async def referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return

    global BOT_USERNAME
    if not BOT_USERNAME:
        me = await context.bot.get_me()
        BOT_USERNAME = me.username

    user = query.from_user
    link = f"https://t.me/{BOT_USERNAME}?start={user.id}"
    count = storage.get_referral_count(user.id)

    await query.edit_message_text(
        "🔗 رابط الدعوة الخاص بك:\n\n"
        f"`{link}`\n\n"
        "👆 انسخ الرابط وشاركه مع أصدقائك!\n\n"
        f"📊 عدد من دعوتهم حتى الآن: *{count}* شخص",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 إحصائياتي", callback_data="referral_stats")],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
        ]),
    )


async def referral_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return

    user = query.from_user
    count = storage.get_referral_count(user.id)

    if count == 0:
        status = "لم تدعُ أحداً بعد. ابدأ الآن وشارك رابطك!"
    elif count < 5:
        status = "بداية رائعة! استمر في المشاركة لزيادة فرصك."
    elif count < 20:
        status = "أداء ممتاز! أنت في طريقك للفوز بالجائزة."
    else:
        status = "مذهل! أنت من أكثر المدعوين نشاطاً. 🏆"

    await query.edit_message_text(
        f"📊 إحصائياتي — {user.first_name}\n\n"
        f"👥 إجمالي المدعوين: *{count}* شخص\n\n"
        f"💬 {status}\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🏆 الجوائز تُعلن دورياً في @Trad_2win",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 رابط الدعوة الخاص بي", callback_data="referral_link")],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
        ]),
    )


# ─────────────────────────────────────────────
#  AI GOLD ANALYSIS
# ─────────────────────────────────────────────

async def menu_gold_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return

    await query.edit_message_text(
        "📊 جارٍ تحليل بيانات الذهب XAU/USD (4H)...\n\n"
        "⏳ يرجى الانتظار — يتم حساب المؤشرات الفنية..."
    )

    loop = asyncio.get_event_loop()
    from gold_analysis import get_gold_analysis, TRADINGVIEW_URL
    text, chart_bytes = await loop.run_in_executor(None, get_gold_analysis)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 فتح الشارت المباشر (TradingView)", url=TRADINGVIEW_URL)],
        [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
    ])

    if chart_bytes:
        await query.message.reply_photo(
            photo=InputFile(BytesIO(chart_bytes), filename="gold_chart_4h.png"),
            caption=text,
            reply_markup=kb,
        )
        try:
            await query.delete_message()
        except Exception:
            pass
    else:
        await query.edit_message_text(text, reply_markup=kb)


# ─────────────────────────────────────────────
#  USDT DEPOSIT / WITHDRAWAL
# ─────────────────────────────────────────────

async def menu_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    await query.edit_message_text(
        "💳 إيداع وسحب USDT\n\n"
        "نقدم خدمات الإيداع والسحب بعملة USDT عبر شبكة TRC20 "
        "بسرعة وأمان تامّين.\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "✅ الشبكة المدعومة: TRC20 (Tron)\n"
        "✅ الحد الأدنى للإيداع: 20 USDT\n"
        "✅ الحد الأدنى للسحب: 20 USDT\n"
        "✅ وقت المعالجة: خلال ساعة عمل واحدة\n"
        "✅ رسوم تحويل: صفر من طرفنا\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📌 للبدء في عملية الإيداع أو السحب،\n"
        "تواصل مع موظف الدعم مباشرةً:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "تواصل مع موظف الدعم 🎧",
                url="https://t.me/B_T2w"
            )],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
        ]),
    )


# ─── Monaxa Direct Support ────────────────────────────────────────────────────

async def menu_monaxa_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    # Track support section views for the daily report
    asyncio.create_task(storage.async_record_support_click(query.from_user.id))
    await query.edit_message_text(
        "مرحباً بك في قسم الدعم الفني الخاص بشركة Monaxa 🎧\n\n"
        "يسعدنا خدمتك وتسهيل تجربتك التداولية. يمكنك التواصل الآن مباشرة مع "
        "الفريق المختص للحصول على مساعدة فورية بخصوص:\n\n"
        "✅ فتح وتوثيق الحسابات.\n"
        "💰 عمليات الإيداع والسحب.\n"
        "📈 الاستفسارات التقنية حول منصة التداول.\n"
        "🎁 تفعيل البونص والمكافآت.\n\n"
        "فريق الدعم متواجد لخدمتكم لضمان أفضل تجربة مع Trade 2 Win. "
        "اضغط على الزر أدناه لبدء المحادثة عبر واتساب مباشرة: 👇",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "💬 تواصل عبر واتساب",
                url="https://wa.me/34605200329",
            )],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
        ]),
    )


# ─── Open Account (intermediate page with post-registration instructions) ────

async def menu_open_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    # Track link page views for the daily report
    asyncio.create_task(storage.async_record_link_click(query.from_user.id))
    await query.edit_message_text(
        "🏦 *فتح حساب تحت وكالة Trade 2 Win*\n\n"
        "انقر على الزر أدناه للتسجيل عبر الرابط الرسمي لوكالة *Trade 2 Win* في شركة *Monaxa*:\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📋 *خطوات ما بعد التسجيل:*\n\n"
        "1️⃣ أكمل عملية التسجيل والتوثيق.\n"
        "2️⃣ قم بأول إيداع لتفعيل حسابك.\n"
        "3️⃣ أرسل رقم حسابك *(UID)* إلى الدعم:\n"
        "     👉 @B\\_T2w\n\n"
        "🎁 *ستحصل على:*\n"
        "✅ مكافآت إيداع حصرية لمشتركي بوت Trade 2 Win.\n"
        "🎡 *5 محاولات إضافية* في عجلة الحظ!\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💡 بعد إتمام التسجيل والإيداع، أرسل رقم حسابك (UID) إلى الدعم "
        "@B\\_T2w للحصول على مكافآت حصرية وعدد 5 محاولات إضافية في عجلة الحظ! 🎡",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("سجّل الآن 🚀", url=MONAXA_REG_URL)],
            [InlineKeyboardButton("تواصل مع الدعم 🎧", url="https://t.me/B_T2w")],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
        ]),
    )


# ─── Why Monaxa ───────────────────────────────────────────────────────────────

async def menu_why_monaxa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    await query.edit_message_text(
        "لماذا تعتبر Monaxa الخيار الأول للمتداولين المحترفين؟ 💎\n\n"
        "انضمامك لشركة *Monaxa* من خلال مشروع *Trade 2 Win* يمنحك مزايا استثنائية:\n\n"
        "🛡️ *تراخيص عالمية:* بيئة تداول آمنة ومنظمة تضمن حقوقك.\n\n"
        "⚡ *تنفيذ فائق السرعة:* وداعاً للانزلاقات السعرية، تنفيذ الأوامر يتم في أجزاء من الثانية.\n\n"
        "💰 *أقل سبريد (Spread):* ابدأ التداول بأقل تكلفة ممكنة لتعظيم أرباحك.\n\n"
        "🚀 *رافعة مالية مرنة:* تصل إلى *1:2000* لتناسب جميع استراتيجيات التداول.\n\n"
        "💳 *سحب وإيداع فوري:* دعم كامل لجميع الوسائل المحلية والعالمية "
        "(USDT, Crypto, Bank Cards).\n\n"
        "🎁 *بونص حصري:* احصل على مكافآت إيداع خاصة لمشتركي بوت Trade 2 Win.\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "ابدأ رحلة النجاح الآن وحول شغفك إلى أرباح حقيقية! 🌟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 أنواع الحسابات المتاحة", callback_data="menu_account_types")],
            [InlineKeyboardButton("فتح حساب حقيقي الآن 🚀",   callback_data="menu_open_account")],
            [InlineKeyboardButton("تواصل مع الدعم للاستفسار 🎧", url="https://wa.me/34605200329")],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
        ]),
    )


# ─── Account Types ────────────────────────────────────────────────────────────

async def menu_account_types(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return
    await query.edit_message_text(
        "📋 *أنواع الحسابات المتاحة في Monaxa*\n\n"
        "اختر الحساب الذي يناسب استراتيجيتك وأهدافك التداولية:\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "🎁 *حساب Welcome Bonus*\n"
        "   يمنحك بونص *50$* حقيقي قابل للتداول والخسارة.\n"
        "   (فقط أودع *25$* واحصل على بونص *50$* إضافية، مع إمكانية سحب الأرباح لغاية *100$*).\n\n"
        "♾️ *حساب Lifetime Bonus*\n"
        "   يمنحك بونص حقيقي قابل للتداول والخسارة بنسبة *50%* (للمبالغ لغاية *500$*) "
        "وبنسبة *30%* (للمبالغ لغاية *20,000$*).\n\n"
        "⚡ *Zero Account*\n"
        "   سبريد يبدأ من *0.0 نقطة* — الخيار المثالي لمتداولي السكالبينج والتداول السريع.\n\n"
        "🟦 *Standard Account*\n"
        "   الحساب الكلاسيكي المثالي لجميع أنواع الاستراتيجيات وجميع مستويات الخبرة.\n\n"
        "💎 *Pro Account*\n"
        "   خصائص متقدمة وتنفيذ فائق السرعة — مصمم خصيصاً للمتداولين المحترفين.\n\n"
        "🪙 *Cent Account*\n"
        "   مثالي للمبتدئين ولتجربة الاستراتيجيات بأقل مخاطر ممكنة.\n\n"
        "🚀 *10x Booster Account*\n"
        "   ضاعف قدرتك التداولية مع نظام التعزيز الفريد لتحقيق أرباح استثنائية.\n\n"
        "💼 *Prop Firm — الحسابات الممولة*\n"
        "   احصل على تمويل حقيقي للتداول وحقق أرباحاً فعلية بعد اجتياز تحدي التأهيل.\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🚀 *الرافعة المالية:* تصل إلى *1:2000* عبر وكالة Trade 2 Win.\n"
        "💳 *الإيداع والسحب:* USDT · Crypto · Bank Cards · محافظ محلية.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("فتح حسابك المفضل الآن 📈", url=MONAXA_REG_URL)],
            [InlineKeyboardButton("تواصل مع الدعم للاستفسار 🎧", url="https://wa.me/34605200329")],
            [InlineKeyboardButton("🔙 العودة — لماذا Monaxa؟", callback_data="menu_why_monaxa")],
            [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu_main")],
        ]),
    )


# ─────────────────────────────────────────────
#  ADMIN DASHBOARD  (/admin)
# ─────────────────────────────────────────────

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _is_admin(user.id):
        return  # Silently ignore non-admins

    await update.message.reply_text(
        "🔐 لوحة تحكم المدير\n\n"
        "مرحباً! اختر ما تريد القيام به:",
        reply_markup=admin_menu_keyboard(),
    )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return

    data = storage._load()
    total = storage.get_total_users()
    approved = len(data["approved_users"])
    pending = len(data["pending_kyc"])
    rejected = total - approved - pending
    total_referrals = sum(data["referrals"].values()) if data["referrals"] else 0
    users_with_referrals = len([v for v in data["referrals"].values() if v > 0])

    await query.edit_message_text(
        "📊 إحصائيات البوت\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 إجمالي المستخدمين: *{total}*\n"
        f"✅ تم التحقق منهم (KYC): *{approved}*\n"
        f"⏳ قيد المراجعة: *{pending}*\n"
        f"❌ غير مكتمل/مرفوض: *{rejected}*\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 إجمالي الدعوات: *{total_referrals}*\n"
        f"🙋 مستخدمون لديهم دعوات: *{users_with_referrals}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_back")]
        ]),
    )


async def admin_top_referrers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return

    top = storage.get_top_referrers(10)
    if not top:
        lines = "لا توجد بيانات دعوة بعد.\nانتظر حتى يبدأ المستخدمون بمشاركة روابطهم."
    else:
        medals = ["🥇", "🥈", "🥉"]
        lines = ""
        for i, (uid, name, count) in enumerate(top, 1):
            medal = medals[i - 1] if i <= 3 else f"{i}."
            invite_word = "دعوة" if count == 1 else "دعوات"
            lines += f"{medal} *{name}* — {count} {invite_word}\n"
            lines += f"     `ID: {uid}`\n\n"

    await query.edit_message_text(
        "🏅 قائمة المتصدرين — أكثر 10 مستخدمين دعوةً\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        + lines,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_back")]
        ]),
    )


async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return
    await query.edit_message_text(
        "🔐 لوحة تحكم المدير\n\nاختر ما تريد القيام به:",
        reply_markup=admin_menu_keyboard(),
    )


# ─── Broadcast helpers ───

async def _run_broadcast(context, users: list, send_fn, progress_msg) -> tuple[int, int]:
    """Send to all users with a live progress counter edited every 10 users."""
    total = len(users)
    success, fail = 0, 0
    UPDATE_EVERY = max(1, min(10, total // 10 or 1))

    for i, uid in enumerate(users, 1):
        try:
            await send_fn(uid)
            success += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)

        if i % UPDATE_EVERY == 0 or i == total:
            try:
                await progress_msg.edit_text(
                    f"📡 جارٍ الإرسال...\n\n"
                    f"⏳ تم الإرسال: {i} / {total}\n"
                    f"✅ نجح: {success}   ❌ فشل: {fail}"
                )
            except Exception:
                pass

    return success, fail


# ─── Broadcast: text ───

async def admin_broadcast_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return
    context.user_data["broadcast_mode"] = "text"
    await query.edit_message_text(
        "📣 إرسال منشور نصي للكل\n\n"
        "اكتب الرسالة التي تريد إرسالها لجميع المستخدمين.\n"
        "يمكنك استخدام *굵게* و_مائل_ وغيرها من تنسيقات Markdown.\n\n"
        "للإلغاء اكتب /cancel"
    )
    return BROADCAST_TEXT


async def admin_broadcast_text_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    msg_text = update.message.text
    users = storage.get_all_users()

    progress_msg = await update.message.reply_text(
        f"📡 جارٍ الإرسال...\n\n⏳ تم الإرسال: 0 / {len(users)}\n✅ نجح: 0   ❌ فشل: 0"
    )

    async def send_fn(uid):
        await context.bot.send_message(chat_id=uid, text=msg_text)

    success, fail = await _run_broadcast(context, users, send_fn, progress_msg)

    await progress_msg.edit_text(
        "✅ اكتمل الإرسال!\n\n"
        f"👥 إجمالي المستخدمين: {len(users)}\n"
        f"📨 نجح الإرسال: {success}\n"
        f"❌ فشل: {fail}"
    )
    await update.message.reply_text("العودة إلى لوحة التحكم:", reply_markup=admin_menu_keyboard())
    context.user_data.pop("broadcast_mode", None)
    return ConversationHandler.END


# ─── Broadcast: photo ───

async def admin_broadcast_photo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return
    context.user_data["broadcast_mode"] = "photo"
    await query.edit_message_text(
        "🖼️ إرسال صورة للكل\n\n"
        "أرسل الصورة مع تعليق (caption) اختياري.\n\n"
        "للإلغاء اكتب /cancel"
    )
    return BROADCAST_PHOTO


async def admin_broadcast_photo_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    if not update.message.photo:
        await update.message.reply_text("⚠️ يرجى إرسال صورة.")
        return BROADCAST_PHOTO

    photo_id = update.message.photo[-1].file_id
    caption = update.message.caption or ""
    users = storage.get_all_users()

    progress_msg = await update.message.reply_text(
        f"📡 جارٍ الإرسال...\n\n⏳ تم الإرسال: 0 / {len(users)}\n✅ نجح: 0   ❌ فشل: 0"
    )

    async def send_fn(uid):
        await context.bot.send_photo(chat_id=uid, photo=photo_id, caption=caption)

    success, fail = await _run_broadcast(context, users, send_fn, progress_msg)

    await progress_msg.edit_text(
        "✅ اكتمل الإرسال!\n\n"
        f"👥 إجمالي المستخدمين: {len(users)}\n"
        f"📨 نجح الإرسال: {success}\n"
        f"❌ فشل: {fail}"
    )
    await update.message.reply_text("العودة إلى لوحة التحكم:", reply_markup=admin_menu_keyboard())
    context.user_data.pop("broadcast_mode", None)
    return ConversationHandler.END


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("broadcast_mode", None)
    await update.message.reply_text("تم الإلغاء.", reply_markup=admin_menu_keyboard())
    return ConversationHandler.END


# ─── User Lookup ───

async def admin_user_lookup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return
    await query.edit_message_text(
        "🔍 بحث عن مستخدم\n\n"
        "أرسل رقم الـ User ID الخاص بالمستخدم الذي تريد الاستعلام عنه.\n\n"
        "مثال: `123456789`\n\n"
        "للإلغاء اكتب /cancel",
        parse_mode="Markdown",
    )
    return USER_LOOKUP


async def admin_user_lookup_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()
    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text(
            "⚠️ يرجى إرسال رقم User ID صحيح فقط (أرقام فقط).\nحاول مجدداً أو اكتب /cancel للإلغاء."
        )
        return USER_LOOKUP

    info = storage.get_user_referral_info(target_id)

    if not info["is_registered"]:
        status_icon = "❓ غير مسجّل في قاعدة البيانات"
    elif info["is_approved"]:
        status_icon = "✅ معتمد (KYC مكتمل)"
    elif info["is_pending"]:
        status_icon = "⏳ قيد المراجعة"
    else:
        status_icon = "🔴 غير مكتمل"

    invite_count = info["referral_count"]
    invite_word = "دعوة" if invite_count == 1 else "دعوات"

    can_spin_now, _ = storage.can_spin(target_id)
    spin_status = "✅ متاحة الآن" if can_spin_now else "⏳ في انتظار 24 ساعة"

    await update.message.reply_text(
        f"🔍 نتيجة البحث\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 الاسم: *{info['name']}*\n"
        f"🆔 User ID: `{target_id}`\n"
        f"📋 الحالة: {status_icon}\n"
        f"🎡 محاولة العجلة: {spin_status}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 عدد الدعوات الناجحة: *{invite_count}* {invite_word}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("منح محاولة إضافية 🎁", callback_data=f"grant_spin_{target_id}")],
            [InlineKeyboardButton("🔍 بحث عن مستخدم آخر", callback_data="admin_user_lookup")],
            [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_back")],
        ]),
    )
    return ConversationHandler.END


# ─── Admin: Grant Extra Spin ──────────────────────────────────────────────────

async def admin_grant_spin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not _is_admin(query.from_user.id):
        return

    # Extract target user_id from callback_data  e.g. "grant_spin_123456789"
    try:
        target_id = int(query.data.split("grant_spin_", 1)[1])
    except (IndexError, ValueError):
        await query.answer("⚠️ بيانات غير صالحة.", show_alert=True)
        return

    # ── Reset the 24-hour cooldown ──
    await storage.async_reset_spin(target_id)

    # ── Notify the user privately ──
    bot_username = context.bot.username or BOT_USERNAME or "Trade2WinBot"
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                "تهانينا! 🎉\n\n"
                "تقديراً لثقتكم في *Trade 2 Win*، تم منحكم محاولة إضافية مجانية "
                "في عجلة الحظ الآن.\n\n"
                "جرب حظك وقد تكون الجائزة الكبرى من نصيبك! 🎡"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "انتقل للعجلة الآن 🚀",
                    url=f"https://t.me/{bot_username}",
                )
            ]]),
        )
        user_notified = True
    except Exception as e:
        logger.warning(f"Could not notify user {target_id} of spin grant: {e}")
        user_notified = False

    # ── Admin feedback on the dashboard card ──
    note = (
        "تم منح المحاولة بنجاح وإشعار العميل ✅"
        if user_notified
        else "تم إعادة ضبط العجلة ✅ (تعذّر إرسال الإشعار للمستخدم)"
    )
    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ {note}", callback_data="noop")],
            [InlineKeyboardButton("🔍 بحث عن مستخدم آخر", callback_data="admin_user_lookup")],
            [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_back")],
        ])
    )


# ─────────────────────────────────────────────
#  LUCKY WHEEL
# ─────────────────────────────────────────────

WHEEL_PRIZES = [
    ("try_again",  32.0),
    ("vip",        67.0),
    ("money_5",     0.9),
    ("money_10",    0.1),
]

WHEEL_OUTCOMES = {
    "try_again": {
        "emoji":   "🔄",
        "title":   "إعادة محاولة مجانية!",
        "message": (
            "🔄 *إعادة محاولة مجانية!*\n\n"
            "لم تحالفك الحظ هذه المرة، لكن لا تستسلم!\n"
            "ارجع غداً وحظك مع العجلة مرة أخرى. 💪\n\n"
            "تذكّر: الحظ يُحالف المثابرين! 🌟"
        ),
    },
    "vip": {
        "emoji":   "🌟",
        "title":   "دخول قناة VIP!",
        "message": (
            "🌟 *مبروك! فزت بالدخول لقناة Trade 2 Win VIP!*\n\n"
            "ستتلقى دعوة للانضمام للقناة الحصرية قريباً.\n"
            "تابع رسائلك الخاصة خلال 24 ساعة. 🎉\n\n"
            "في القناة VIP:\n"
            "✅ إشارات تداول حصرية\n"
            "✅ تحليلات يومية مباشرة\n"
            "✅ دعم أولوية من الفريق"
        ),
    },
    "money_5": {
        "emoji":   "💰",
        "title":   "جائزة مالية 5$!",
        "message": (
            "💰 *تهانينا! 🎉*\n\n"
            "لقد ربحت جائزة مالية قيمتها *5$*.\n\n"
            "يرجى التواصل مع إدارة البوت فوراً لاستلام جائزتك: @B\\_T2w\n\n"
            "📸 *يرجى تزويدهم بصورة لهذه الرسالة.*"
        ),
    },
    "money_10": {
        "emoji":   "💎",
        "title":   "جائزة مالية 10$!",
        "message": (
            "💎 *تهانينا! 🎉*\n\n"
            "لقد ربحت جائزة مالية قيمتها *10$*.\n\n"
            "يرجى التواصل مع إدارة البوت فوراً لاستلام جائزتك: @B\\_T2w\n\n"
            "📸 *يرجى تزويدهم بصورة لهذه الرسالة.*"
        ),
    },
}

# ── Lucky Wheel: 5-slot horizontal reel ───────────────────────────────────────
#  Slots are fixed; the prize determines which one the pointer lands on.
_WHEEL_SLOTS = [
    ("🔄", "إعادة محاولة"),
    ("🌟", "VIP حصري"),
    ("💰", "جائزة 5$"),
    ("💎", "جائزة 10$"),
    ("🎁", "VIP بلاتيني"),
]
_PRIZE_TO_SLOT = {"try_again": 0, "vip": 1, "money_5": 2, "money_10": 3}


def _make_wheel_frame(active_idx: int, speed_line: str) -> str:
    """Render one animation frame with the pointer【 】on the active slot."""
    parts = []
    for i, (emoji, _label) in enumerate(_WHEEL_SLOTS):
        if i == active_idx:
            parts.append(f"【{emoji}】")
        else:
            parts.append(f"  {emoji}  ")
    row = "  ".join(parts)
    return (
        f"🎰 *عجلة الحظ تدور...*\n\n"
        f"`{row}`\n\n"
        f"{speed_line}"
    )


def _spin_frames(final_key: str) -> tuple[list[str], list[float]]:
    """
    Return (frames, delays).
    6 frames: bounces fast → decelerates → stops at the prize slot.
    The pointer position and speed label simulate a real physical wheel.
    """
    final_idx = _PRIZE_TO_SLOT.get(final_key, 1)

    # Bouncing path that always ends at final_idx (never repeats final early)
    penultimate = (final_idx + 2) % len(_WHEEL_SLOTS)
    path = [2, 4, 0, 3, penultimate, final_idx]

    speed_labels = [
        "⚡⚡⚡ *تدور بسرعة فائقة...*",
        "⚡⚡⚡ *تدور بسرعة فائقة...*",
        "⚡⚡ *تتباطأ...*",
        "⚡⚡ *تتباطأ...*",
        "⚡ *على وشك التوقف...*",
        "🎯 *توقفت! جارٍ الكشف عن الجائزة...*",
    ]
    delays = [0.35, 0.40, 0.55, 0.70, 0.90, 0.95]

    frames = [
        _make_wheel_frame(pos, spd)
        for pos, spd in zip(path, speed_labels)
    ]
    return frames, delays


def _spin_prize() -> str:
    keys   = [p[0] for p in WHEEL_PRIZES]
    weights = [p[1] for p in WHEEL_PRIZES]
    return random.choices(keys, weights=weights, k=1)[0]


def _format_cooldown(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h} ساعة و{m} دقيقة"
    elif m > 0:
        return f"{m} دقيقة و{s} ثانية"
    return f"{s} ثانية"


async def menu_wheel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _require_approved(query):
        return

    user = query.from_user
    can, remaining = await storage.async_can_spin(user.id)

    if not can:
        await query.edit_message_text(
            "🎡 *عجلة الحظ اليومية*\n\n"
            "لقد استنفدت محاولتك اليومية! ⏳\n\n"
            f"عد مجدداً بعد *{_format_cooldown(remaining)}* لمضاعفة أرباحك مع Trade 2 Win.\n\n"
            "🌟 كل يوم فرصة جديدة — لا تفوّتها!",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
        return

    history = storage.get_user_spin_history(user.id)
    vip_wins    = sum(1 for w in history if w["prize"] == "vip")
    money_wins  = sum(1 for w in history if w["prize"] in ("money_5", "money_10"))
    total_spins = len(history)

    is_admin_tester = (user.id == storage.ADMIN_WHEEL_ID)
    spins_line = (
        "♾️ *وضع المدير — محاولات غير محدودة*"
        if is_admin_tester
        else "🎯 لديك محاولة واحدة يومياً — استخدمها بحكمة!"
    )

    await query.edit_message_text(
        "🎡 *عجلة الحظ اليومية*\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "الجوائز المتاحة اليوم:\n\n"
        "🔄 إعادة محاولة مجانية\n"
        "🌟 دخول قناة Trade 2 Win VIP\n"
        "💰 جائزة مالية 5$\n"
        "💎 جائزة مالية 10$\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📊 إجمالي تدويراتك: {total_spins} | 🏆 فوزك بـ VIP: {vip_wins} | 💵 فوزك بمال: {money_wins}\n\n"
        f"{spins_line}\n\n"
        "🍀 هل أنت مستعد؟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎡 أدر العجلة الآن!", callback_data="wheel_spin")],
            [InlineKeyboardButton("فتح حساب & الحصول على 5 محاولات 🎁", callback_data="menu_open_account")],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
        ]),
    )


async def wheel_spin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🎡 جارٍ التدوير...", show_alert=False)
    if not await _require_approved(query):
        return

    user = query.from_user
    can, remaining = await storage.async_can_spin(user.id)
    if not can:
        await query.edit_message_text(
            "🎡 *عجلة الحظ اليومية*\n\n"
            "لقد استنفدت محاولتك اليومية! ⏳\n\n"
            f"عد مجدداً بعد *{_format_cooldown(remaining)}* لمضاعفة أرباحك مع Trade 2 Win.\n\n"
            "🌟 كل يوم فرصة جديدة — لا تفوّتها!",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
        return

    # ── Determine prize BEFORE animation (fixes race-condition) ──
    prize_key = _spin_prize()
    outcome   = WHEEL_OUTCOMES[prize_key]

    # ── Record the spin immediately so double-tap / rapid retries are blocked ──
    update_cd = prize_key != "try_again"
    await storage.async_record_spin(user.id, prize_key, update_cooldown=update_cd)

    # ── Generate a unique verification code tied to this spin ──
    verify_code = f"T2W-{user.id % 9999:04d}-{int(time.time()) % 99999:05d}"

    # ── Decelerating wheel animation (6 frames, slows to a stop) ──
    frames, delays = _spin_frames(prize_key)
    for frame, delay in zip(frames, delays):
        try:
            await query.edit_message_text(frame, parse_mode="Markdown")
        except Exception:
            pass
        await asyncio.sleep(delay)

    # ── Generate certificate image (in thread so we don't block event loop) ──
    from prize_image import generate_prize_image
    loop = asyncio.get_event_loop()
    img_bytes = await loop.run_in_executor(
        None,
        lambda: generate_prize_image(
            prize_key,
            user.full_name,
            BOT_USERNAME or "Trade2WinBot",
            verify_code,
        ),
    )

    # ── Sharing URL ──
    share_text = urllib.parse.quote(
        "🏆 لقد ربحت للتو جائزة في عجلة حظ Trade 2 Win!\n"
        "جرب حظك الآن وربما تفوز بـ VIP أو جائزة مالية!"
    )
    bot_url = urllib.parse.quote(f"https://t.me/{BOT_USERNAME or 'Trade2WinBot'}")
    share_url = f"https://t.me/share/url?url={bot_url}&text={share_text}"

    # ── Try Again — free respin (cooldown not consumed, already recorded above) ──
    if prize_key == "try_again":
        caption = (
            f"🔄 حظاً أوفر يا {user.first_name}! 🎉\n\n"
            "لقد حصلت على دور إضافي مجاني — لا يُحتسب هذا ضمن الـ 24 ساعة.\n"
            "جرب حظك مرة أخرى الآن!"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎡 تدوير العجلة مجدداً!", callback_data="wheel_spin")],
            [InlineKeyboardButton("🔗 مشاركة الفوز مع الأصدقاء", url=share_url)],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
        ])
        await query.message.reply_photo(
            photo=InputFile(BytesIO(img_bytes), filename="prize.png"),
            caption=caption,
            reply_markup=kb,
        )
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # ── Real prize (cooldown already consumed at top of handler) ──
    is_money_prize = prize_key in ("money_5", "money_10")
    amount = 5 if prize_key == "money_5" else 10 if prize_key == "money_10" else 0

    caption = (
        f"تهانينا {user.first_name}! 🎉\n\n"
        "لقد ربحت الجائزة الموضحة في الشهادة.\n"
        "تفضل بمشاركتها مع أصدقائك!"
    )

    if is_money_prize:
        caption += (
            f"\n\n💰 جائزتك {amount}$ — تواصل مع الإدارة فوراً لاستلامها.\n"
            "📸 أرسل صورة من هذه الشهادة للتحقق."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("تواصل مع الإدارة 🎧", url="https://t.me/B_T2w")],
            [InlineKeyboardButton("🔗 مشاركة الفوز مع الأصدقاء", url=share_url)],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
        ])
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 مشاركة الفوز مع الأصدقاء", url=share_url)],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="menu_main")],
        ])

    await query.message.reply_photo(
        photo=InputFile(BytesIO(img_bytes), filename="prize.png"),
        caption=caption,
        reply_markup=kb,
    )
    try:
        await query.message.delete()
    except Exception:
        pass

    # ── Admin notifications ──
    import datetime
    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    username_str = f"@{user.username}" if user.username else "N/A"

    if prize_key == "vip":
        vip_alert = (
            "🌟 فوز بقناة VIP — يرجى إضافة المستخدم\n\n"
            f"👤 اسم الفائز: {user.full_name}\n"
            f"📛 معرف الحساب: {username_str}\n"
            f"🆔 رقم الآيدي: {user.id}\n\n"
            "📌 الإجراء المطلوب: أضف المستخدم لقناة Trade 2 Win VIP"
        )
        for chat_id in [ADMIN_GROUP_ID, ADMIN_USER_ID]:
            try:
                await context.bot.send_message(chat_id=chat_id, text=vip_alert)
            except Exception as e:
                logger.error(f"VIP admin notify failed for {chat_id}: {e}")

    elif is_money_prize:
        # Log to secure ledger first (async I/O)
        prize_id = await storage.async_log_financial_prize(
            user_id=user.id,
            full_name=user.full_name,
            username=user.username or "",
            prize_key=prize_key,
            amount=amount,
        )

        urgency = "🚨🚨" if prize_key == "money_10" else "🚨"
        money_alert = (
            f"{urgency} تنبيه عاجل — فائز بجائزة مالية {amount}$\n"
            "━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 اسم الفائز: {user.full_name}\n"
            f"📛 معرف الحساب: {username_str}\n"
            f"🆔 رقم الآيدي: {user.id}\n"
            f"🏆 نوع الجائزة: {amount}$ نقداً\n"
            f"🕐 الوقت: {now_str}\n"
            f"🔑 رمز التحقق: {prize_id}\n"
            f"📜 رمز الشهادة: {verify_code}\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "📌 الإجراء المطلوب: تحقق من رمز التحقق في لوحة التحكم "
            "ثم أرسل الجائزة للمستخدم عبر Monaxa."
        )
        for chat_id in [ADMIN_GROUP_ID, ADMIN_USER_ID]:
            try:
                await context.bot.send_message(chat_id=chat_id, text=money_alert)
            except Exception as e:
                logger.error(f"Money prize admin notify failed for {chat_id}: {e}")


# ─── Admin: Prizes Ledger ───

async def admin_prizes_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return

    import datetime
    prizes = storage.get_financial_prizes()

    if not prizes:
        body = "لا توجد جوائز مالية مسجّلة بعد."
    else:
        body = ""
        for p in prizes[:10]:
            ts = datetime.datetime.utcfromtimestamp(p["timestamp"]).strftime("%Y-%m-%d %H:%M")
            uname = f"@{p['username']}" if p.get("username") and p["username"] != "N/A" else "N/A"
            body += (
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🔑 {p['prize_id']}\n"
                f"👤 {p['full_name']} ({uname})\n"
                f"🆔 {p['user_id']}\n"
                f"💵 الجائزة: {p['amount_usd']}$\n"
                f"🕐 {ts} UTC\n"
                f"📋 الحالة: {p.get('status', 'pending')}\n\n"
            )
        if len(prizes) > 10:
            body += f"... و{len(prizes) - 10} جائزة أخرى سابقة\n"

    total_pending = sum(p["amount_usd"] for p in prizes if p.get("status") == "pending")
    total_all = sum(p["amount_usd"] for p in prizes)

    await query.edit_message_text(
        f"💵 سجل الجوائز المالية\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📦 إجمالي الجوائز: *{len(prizes)}* | المجموع: *{total_all}$*\n"
        f"⏳ غير مُسوّاة: *{total_pending}$*\n\n"
        + body,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_back")]
        ]),
    )


# ─── Admin: Wheel Stats ───

async def admin_wheel_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return

    stats = storage.get_spin_stats()

    await query.edit_message_text(
        "🎡 إحصائيات عجلة الحظ\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎰 إجمالي التدويرات: *{stats['total_spins']}*\n"
        f"👥 مستخدمون دوّروا العجلة: *{stats['unique_spinners']}*\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📊 توزيع الجوائز:\n\n"
        f"🔄 إعادة محاولة: *{stats['try_again']}* مرة\n"
        f"🌟 فوز بـ VIP: *{stats['vip']}* مرة\n"
        f"💰 فوز بـ 5$: *{stats['money_5']}* مرة\n"
        f"💎 فوز بـ 10$: *{stats['money_10']}* مرة\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"💵 إجمالي الجوائز المالية المُسلّمة: *{stats['prize_money_total']}$*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_back")]
        ]),
    )


# ─────────────────────────────────────────────
#  DAILY REPORT
# ─────────────────────────────────────────────

async def send_daily_report(context) -> None:
    """Scheduled job: sends a 24-hour performance report to the admin at 09:00."""
    since_ts = datetime.datetime.now().timestamp() - 86400  # last 24 hours
    try:
        stats = await storage.async_get_daily_stats(since_ts)
    except Exception as exc:
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=f"⚠️ تعذّر إنشاء التقرير اليومي:\n`{exc}`",
            parse_mode="Markdown",
        )
        return

    now_str = datetime.datetime.now().strftime("%Y-%m-%d")
    money_prize_line = (
        f"    • جوائز 5$:  *{stats['money_5_wins']}* فائز\n"
        f"    • جوائز 10$: *{stats['money_10_wins']}* فائز"
    )

    report = (
        "📊 *تقرير الأداء اليومي — Trade 2 Win*\n"
        f"📅 التاريخ: `{now_str}`\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 *المستخدمون الجدد:* *{stats['new_users']}* منضم خلال 24 ساعة\n"
        f"   _(الإجمالي الكلي: {stats['total_users']} | الموثقون: {stats['approved_users']})_\n\n"
        f"🎡 *عجلة الحظ:* *{stats['total_spins']}* تدويرة\n\n"
        f"💰 *الجوائز المالية:*\n{money_prize_line}\n\n"
        f"📈 *رابط الوكالة (Monaxa):* *{stats['link_clicks']}* نقرة على صفحة التسجيل\n\n"
        f"🎧 *الدعم الفني:* *{stats['support_clicks']}* طلب دعم Monaxa\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🔐 _هذا التقرير حصري للمدير — Trade 2 Win_"
    )

    await context.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=report,
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    # KYC conversation
    kyc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(verify_button, pattern="^start_kyc$")],
        states={
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_full_name)],
            ID_PHOTO:  [MessageHandler(filters.PHOTO, receive_id_photo)],
        },
        fallbacks=[CommandHandler("cancel", cancel_kyc)],
        per_message=False,
    )

    # Broadcast conversation (admin only)
    broadcast_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_broadcast_text_start,  pattern="^admin_broadcast_text$"),
            CallbackQueryHandler(admin_broadcast_photo_start, pattern="^admin_broadcast_photo$"),
        ],
        states={
            BROADCAST_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_text_send)],
            BROADCAST_PHOTO: [MessageHandler(filters.PHOTO, admin_broadcast_photo_send)],
        },
        fallbacks=[CommandHandler("cancel", cancel_broadcast)],
        per_message=False,
    )

    # User lookup conversation (admin only)
    lookup_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_user_lookup_start, pattern="^admin_user_lookup$"),
        ],
        states={
            USER_LOOKUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_user_lookup_result)],
        },
        fallbacks=[CommandHandler("cancel", cancel_broadcast)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(kyc_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(lookup_conv)

    # Admin decisions on KYC
    app.add_handler(CallbackQueryHandler(admin_decision, pattern="^(accept|reject)_"))

    # Admin dashboard callbacks
    app.add_handler(CallbackQueryHandler(admin_stats,           pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_top_referrers,   pattern="^admin_top_referrers$"))
    app.add_handler(CallbackQueryHandler(admin_wheel_stats,     pattern="^admin_wheel_stats$"))
    app.add_handler(CallbackQueryHandler(admin_prizes_ledger,   pattern="^admin_prizes_ledger$"))
    app.add_handler(CallbackQueryHandler(admin_back,            pattern="^admin_back$"))
    app.add_handler(CallbackQueryHandler(admin_grant_spin,      pattern=r"^grant_spin_\d+$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern="^noop$"))

    # Main menu
    app.add_handler(CallbackQueryHandler(show_main_menu,    pattern="^menu_main$"))
    app.add_handler(CallbackQueryHandler(menu_careers,      pattern="^menu_careers$"))
    app.add_handler(CallbackQueryHandler(menu_offers,       pattern="^menu_offers$"))
    app.add_handler(CallbackQueryHandler(menu_ib_transfer,  pattern="^menu_ib_transfer$"))
    app.add_handler(CallbackQueryHandler(menu_contests,     pattern="^menu_contests$"))
    app.add_handler(CallbackQueryHandler(menu_referral,     pattern="^menu_referral$"))
    app.add_handler(CallbackQueryHandler(menu_gold_ai,      pattern="^menu_gold_ai$"))
    app.add_handler(CallbackQueryHandler(menu_usdt,           pattern="^menu_usdt$"))
    app.add_handler(CallbackQueryHandler(menu_wheel,          pattern="^menu_wheel$"))
    app.add_handler(CallbackQueryHandler(menu_monaxa_support, pattern="^menu_monaxa_support$"))
    app.add_handler(CallbackQueryHandler(menu_why_monaxa,      pattern="^menu_why_monaxa$"))
    app.add_handler(CallbackQueryHandler(menu_open_account,    pattern="^menu_open_account$"))
    app.add_handler(CallbackQueryHandler(menu_account_types,   pattern="^menu_account_types$"))
    app.add_handler(CallbackQueryHandler(wheel_spin,        pattern="^wheel_spin$"))

    # Offers sub-menu
    app.add_handler(CallbackQueryHandler(offer_cashback,  pattern="^offer_cashback$"))
    app.add_handler(CallbackQueryHandler(offer_bonus100,  pattern="^offer_bonus100$"))
    app.add_handler(CallbackQueryHandler(offer_bonus50,   pattern="^offer_bonus50$"))

    # Referral
    app.add_handler(CallbackQueryHandler(referral_link,  pattern="^referral_link$"))
    app.add_handler(CallbackQueryHandler(referral_stats, pattern="^referral_stats$"))

    # ── Daily report at 09:00 every day ──────────────────────────────────────
    app.job_queue.run_daily(
        send_daily_report,
        time=datetime.time(hour=9, minute=0, second=0),
        name="daily_admin_report",
    )

    logger.info("Trade 2 Win Bot starting...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        poll_interval=0.0,
        timeout=30,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    import time as _time_mod

    keep_alive()   # Flask on port 8000 — keeps Replit container alive

    _BASE_DELAY = 5     # seconds before first retry
    _MAX_DELAY  = 120   # cap backoff at 2 minutes
    _delay      = _BASE_DELAY
    _attempt    = 0

    while True:   # infinite restart loop — never gives up
        # Always start with a fresh event loop so PTB doesn't hit
        # "Event loop is closed" on restart after a crash.
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            _attempt += 1
            logger.info(f"Bot starting (run #{_attempt})…")
            main()
            # main() only returns on a clean shutdown (e.g. Ctrl-C inside asyncio)
            logger.info("Bot exited cleanly. Restarting…")
            _delay = _BASE_DELAY   # reset backoff on clean exit
        except KeyboardInterrupt:
            logger.info("Bot stopped by operator (KeyboardInterrupt).")
            break
        except Exception as _exc:
            logger.error(
                f"Bot crashed on run #{_attempt}: {_exc}",
                exc_info=True,
            )
            logger.info(f"Auto-restarting in {_delay}s…")
            _time_mod.sleep(_delay)
            _delay = min(_delay * 2, _MAX_DELAY)   # exponential backoff
        finally:
            try:
                _loop.close()
            except Exception:
                pass
