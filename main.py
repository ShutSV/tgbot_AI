import asyncio
import os
import logging

import openai
from openai import AsyncOpenAI
from functools import wraps
import tempfile

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command

from settings import settings
from database import MessagesRepository, create_table


client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY,)


async def async_remove(file_path):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, os.remove, file_path)


async def generate_text(prompt) -> str:
    try:
        response = await client.chat.completions.create(model="gpt-4o", messages=prompt)
        return response.choices[0].message.content
    except Exception as e:
        logging.error(e)


router = Router()


def extract_info(handler):
    @wraps(handler)
    async def wrapper(message: types.Message, *args, **kwargs):
        chat_id = message.chat.id
        user_id = message.from_user.id
        full_name = message.from_user.full_name
        text = message.text
        rows = await MessagesRepository.filter(user_id=user_id)
        history = ([{"role": "system",
                     "content": "Ты полезный помощник. Можешь задавать вопросы по одному"
                     }] +
                   [{"role": row.role_user, "content": row.message} for row in rows])
        return await handler(message, chat_id=chat_id, user_id=user_id, full_name=full_name, text=text, history=history, *args, **kwargs)
    return wrapper


@router.message(Command("start"))
async def start_handler(msg: Message):
    await msg.answer("Привет! Отправь мне текст или голосовое сообщение, и я отвечу на него.")


@router.message(F.content_type == types.ContentType.TEXT)
@extract_info
async def message_handler(msg: Message, chat_id: int, user_id: int, full_name: str, text: str, history: str):
    prompt = history + [{"role": "user", "content": text}] if history else [{"role": "user", "content": text}]
    reply_text = await generate_text(prompt)
    await msg.answer(f"{full_name}, {reply_text}")
    await MessagesRepository.add({
        "chat_id": chat_id,
        "user_id": user_id,
        "role_user": "user",
        "message": text
    })
    await MessagesRepository.add({
        "chat_id": chat_id,
        "user_id": user_id,
        "role_user": "assistant",
        "message": reply_text
    })


@router.message(F.content_type == types.ContentType.VOICE)
@extract_info
async def voice_handler(msg: Message, bot: Bot, chat_id: int, user_id: int, full_name: str, text: str, history: str):
    # INPUT_VOICE = f"input_{ulid()}.ogg"
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as input_voice:
        INPUT_VOICE = input_voice.name
    try:

        voice_file = await bot.get_file(msg.voice.file_id)
        voice_bytes = await bot.download_file(voice_file.file_path)
        with open(INPUT_VOICE, "wb") as f:
            f.write(voice_bytes.read())
        with open(INPUT_VOICE, "rb") as audio_file:
            transcription = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        prompt = history + [{"role": "user", "content": transcription.text}] if history else [{"role": "user", "content": transcription.text}]
        reply_text = await generate_text(prompt)
        await msg.answer(f"{full_name}, {reply_text}")
        await MessagesRepository.add({
            "chat_id": chat_id,
            "user_id": user_id,
            "role_user": "user",
            "message": transcription.text
        })
        await MessagesRepository.add({
            "chat_id": chat_id,
            "user_id": user_id,
            "role_user": "assistant",
            "message": reply_text
        })
        response = await client.audio.speech.create(
            model="tts-1-hd",
            voice="onyx",
            input=reply_text
        )
        # OUTPUT_VOICE = f"output_{ulid()}.ogg"
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as output_voice:
            OUTPUT_VOICE = output_voice.name

        with open(OUTPUT_VOICE, "wb") as audio_file:
            audio_file.write(response.read())
        audio = FSInputFile(OUTPUT_VOICE)
        await bot.send_audio(msg.chat.id, audio)

    except openai.PermissionDeniedError as e:
        print(f"Permission Denied Error: {e}")
        await msg.answer("К сожалению, эта функция недоступна в вашем регионе.")
    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        try:
            await async_remove(INPUT_VOICE)
        except FileNotFoundError:
            print(f"Файл {INPUT_VOICE} не найден.")
        except UnboundLocalError:
            print("Переменная INPUT_VOICE не определена.")
        try:
            await async_remove(OUTPUT_VOICE)
        except FileNotFoundError:
            print(f"Файл {OUTPUT_VOICE} не найден.")
        except UnboundLocalError:
            print("Переменная OUTPUT_VOICE не определена.")


async def main():
    await create_table()
    bot = Bot(token=settings.TELEGRAM_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
