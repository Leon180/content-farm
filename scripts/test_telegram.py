"""Quick smoke test — send a message via Telegram bot."""

import asyncio
import os

from dotenv import load_dotenv

from content_farm.telegram.bot import TelegramBot

load_dotenv()


async def main() -> None:
    token = os.getenv("CF_TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("CF_TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("ERROR: CF_TELEGRAM_BOT_TOKEN 和 CF_TELEGRAM_CHAT_ID 必須設定在 .env")
        return

    bot = TelegramBot(token=token, chat_id=chat_id)
    msg_id = await bot.send_message("🤖 Content Farm Telegram 連線測試成功！")
    print(f"訊息已發送 (message_id={msg_id})")

    print("等待你回覆任意文字（30 秒內）...")
    try:
        reply = await bot.wait_for_reply(timeout_seconds=30)
        print(f"收到回覆：{reply!r}")
    except TimeoutError:
        print("超時，未收到回覆（但發送功能正常）")


if __name__ == "__main__":
    asyncio.run(main())
