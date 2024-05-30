import asyncio
import logging

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command

from openai import AsyncOpenAI

from dotenv import load_dotenv
from pydantic_settings import BaseSettings


load_dotenv()


class Settings(BaseSettings):
    TELEGRAM_TOKEN: str
    OPENAI_API_KEY: str
    INPUT_VOICE: str
    OUTPUT_VOICE: str


settings = Settings()

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY,)


async def generate_text(prompt) -> str:
    try:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ]
        response = await client.chat.completions.create(model="gpt-4o", messages=messages)
        return response.choices[0].message.content
    except Exception as e:
        logging.error(e)


router = Router()


@router.message(Command("start"))
async def start_handler(msg: Message):
    await msg.answer("Привет! Отправь мне любое сообщение")


@router.message(F.content_type == types.ContentType.TEXT)
async def message_handler(msg: Message):
    reply_text = await generate_text(msg.text)
    await msg.answer(f"Ответ AI: {reply_text}")


@router.message(F.content_type == types.ContentType.VOICE)
async def voice_handler(msg: Message, bot: Bot):
    voice_file = await bot.get_file(msg.voice.file_id)
    voice_bytes = await bot.download_file(voice_file.file_path)
    with open(settings.INPUT_VOICE, "wb") as f:
        f.write(voice_bytes.read())
    with open(settings.INPUT_VOICE, "rb") as audio_file:
        transcription = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
    reply_text = await generate_text(transcription.text)
    await msg.answer(f"Ответ AI: {reply_text}")
    response = await client.audio.speech.create(
        model="tts-1-hd",
        voice="onyx",
        input=reply_text
    )
    with open(settings.OUTPUT_VOICE, "wb") as audio_file:
        audio_file.write(response.read())
    audio = FSInputFile(settings.OUTPUT_VOICE)
    await bot.send_audio(msg.chat.id, audio)


async def main():
    bot = Bot(token=settings.TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
