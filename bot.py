```python
import asyncio
import html
import logging
import os

from supabase import create_client
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)


# ============================================================
# CONFIGURATION
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]


# ============================================================
# SUPABASE CONNECTION
# ============================================================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe(value):
    """Escape text for Telegram HTML."""
    if value is None:
        return ""

    return html.escape(str(value))


def format_list(value):
    """Format Supabase array fields."""
    if not value:
        return "None"

    if isinstance(value, list):
        return ", ".join(str(x) for x in value)

    return str(value)


def format_item(item):
    """Create the Telegram message for an inventory item."""

    name = safe(item.get("name", "Unnamed item"))
    item_id = safe(item.get("id", ""))
    tag = safe(item.get("tag") or "None")

    quantity = item.get("quantity", 0)

    # Price
    try:
        price = f"${float(item.get('price', 0)):,.2f}"
    except (TypeError, ValueError):
        price = "N/A"

    # Cost
    try:
        cost = f"${float(item.get('cost', 0)):,.2f}"
    except (TypeError, ValueError):
        cost = "N/A"

    colors = safe(format_list(item.get("colors")))
    sizes = safe(format_list(item.get("sizes")))
    notes = safe(item.get("notes") or "None")

    created_at = item.get("created_at")

    text = (
        f"📦 <b>{name}</b>\n"
        f"\n"
        f"🏷 <b>Tag:</b> {tag}\n"
        f"🆔 <b>ID:</b> {item_id}\n"
        f"💰 <b>Price:</b> {price}\n"
        f"💵 <b>Cost:</b> {cost}\n"
        f"📊 <b>Quantity:</b> {safe(quantity)}\n"
        f"\n"
        f"🎨 <b>Colors:</b> {colors}\n"
        f"📏 <b>Sizes:</b> {sizes}\n"
        f"\n"
        f"📝 <b>Notes:</b> {notes}"
    )

    if created_at:
        text += f"\n📅 <b>Created:</b> {safe(created_at)}"

    return text


# ============================================================
# /START
# ============================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        "👋 <b>Leen Store Inventory Bot</b>\n\n"
        "Use the following command:\n\n"
        "🏷 <code>/tag d105</code>\n\n"
        "The bot will find the item with that tag "
        "and send all available information."
    )

    if update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML
        )


# ============================================================
# /HELP
# ============================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        "📚 <b>Leen Inventory Commands</b>\n\n"
        "🏷 <code>/tag d105</code>\n"
        "Find an item by tag.\n\n"
        "Example:\n"
        "<code>/tag d105</code>"
    )

    if update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML
        )


# ============================================================
# /TAG
# ============================================================

async def tag_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    # ========================================================
    # NO TAG SUPPLIED
    # ========================================================

    if not context.args:

        await update.message.reply_text(
            "❌ Please enter an item tag.\n\n"
            "Example:\n"
            "<code>/tag d105</code>",
            parse_mode=ParseMode.HTML
        )

        return

    # ========================================================
    # GET TAG
    # ========================================================

    tag = " ".join(context.args).strip()

    if not tag:
        await update.message.reply_text(
            "❌ Please enter an item tag.\n\n"
            "Example:\n"
            "<code>/tag d105</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # ========================================================
    # SEARCHING MESSAGE
    # ========================================================

    searching = await update.message.reply_text(
        f"🔎 Searching for <code>{safe(tag)}</code>...",
        parse_mode=ParseMode.HTML
    )

    try:

        # ====================================================
        # SEARCH SUPABASE
        # ====================================================

        result = (
            supabase
            .table("items")
            .select("*")
            .eq("tag", tag)
            .execute()
        )

        items = result.data or []

        # ====================================================
        # NOTHING FOUND
        # ====================================================

        if not items:

            await searching.edit_text(
                f"❌ No item found with tag "
                f"<code>{safe(tag)}</code>.",
                parse_mode=ParseMode.HTML
            )

            return

        # ====================================================
        # DELETE SEARCH MESSAGE
        # ====================================================

        try:
            await searching.delete()
        except Exception:
            pass

        # ====================================================
        # SEND RESULTS
        # ====================================================

        for item in items:

            text = format_item(item)

            image_url = item.get("image_url")

            # =================================================
            # IMAGE
            # =================================================

            if image_url:

                try:

                    await update.message.reply_photo(
                        photo=image_url,
                        caption=text,
                        parse_mode=ParseMode.HTML
                    )

                except Exception as image_error:

                    logger.warning(
                        "Could not send image: %s",
                        image_error
                    )

                    # Send information without image
                    await update.message.reply_text(
                        text,
                        parse_mode=ParseMode.HTML
                    )

            # =================================================
            # NO IMAGE
            # =================================================

            else:

                await update.message.reply_text(
                    text,
                    parse_mode=ParseMode.HTML
                )

    except Exception as error:

        logger.exception("Database error")

        try:
            await searching.edit_text(
                "❌ Database error:\n\n"
                f"<code>{safe(error)}</code>",
                parse_mode=ParseMode.HTML
            )

        except Exception:

            await update.message.reply_text(
                "❌ Something went wrong while searching."
            )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Telegram error: %s",
        context.error
    )


# ============================================================
# RUN BOT
# ============================================================

async def run_bot():

    application = (
        Application
        .builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # ========================================================
    # COMMANDS
    # ========================================================

    application.add_handler(
        CommandHandler("start", start_command)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("tag", tag_command)
    )

    # ========================================================
    # ERROR HANDLER
    # ========================================================

    application.add_error_handler(error_handler)

    # ========================================================
    # START
    # ========================================================

    print("==========================================")
    print("       LEEN INVENTORY TELEGRAM BOT")
    print("==========================================")
    print("✅ Supabase configured")
    print("✅ Telegram bot starting...")
    print("")
    print("Bot is now running.")
    print("")
    print("Commands:")
    print("/start")
    print("/help")
    print("/tag d105")
    print("")
    print("==========================================")

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # ========================================================
    # KEEP BOT RUNNING
    # ========================================================

    try:

        while True:
            await asyncio.sleep(3600)

    except asyncio.CancelledError:
        pass

    finally:

        await application.updater.stop()
        await application.stop()
        await application.shutdown()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    asyncio.run(run_bot())
```
