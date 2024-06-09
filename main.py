import asyncio
import logging
import os
import tempfile
from functools import wraps
from openai import AsyncOpenAI, PermissionDeniedError
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile

from settings import settings
from database import create_table, UserChatRepository


client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY,)
router = Router()


def extract_info(handler):
    @wraps(handler)
    async def wrapper(message: types.Message, *args, **kwargs):
        try:
            rows = await UserChatRepository.filter(user_id=message.from_user.id)
            if rows:
                assistant_id = rows[0].assistant_id
                thread_id = rows[0].thread_id
                return await handler(
                    message,
                    assistant_id=assistant_id,
                    thread_id=thread_id,
                    *args, **kwargs
                )
            else:
                print("Пользователь не найден.")
                await message.answer("Вначале набери /start")
        except UnboundLocalError:
            print("Переменные assistant_id и thread_id не определены.")
            await message.answer("Вначале набери /start")
    return wrapper


async def async_remove(file_path):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, os.remove, file_path)


async def user_message(thread_id: str, text: str):
    await client.beta.threads.messages.create(
      thread_id=thread_id,
      role="user",
      content=text
    )


async def run(assistant_id: str, thread_id: str, instructions: str = None):
    result = await client.beta.threads.runs.create_and_poll(
      thread_id=thread_id,
      assistant_id=assistant_id,
      instructions=instructions
    )
    if result.status == 'completed':
        messages = await client.beta.threads.messages.list(thread_id=thread_id)
        return messages.data[0].content[0].text.value
    else:
        print(result.status)
        return "Повторите вопрос, пожалуйста."


@router.message(Command("start"))
async def start_handler(message: Message):
    assistant = await client.beta.assistants.create(
        name="Math Tutor",
        instructions="You are a personal math tutor. Write and run code to answer math questions.",
        tools=[{"type": "code_interpreter"}],
        model="gpt-4o",
    )
    thread = await client.beta.threads.create()
    await message.answer("Привет! Я твой персональный учитель математики. Ставь задачи, и я их решу.")
    try:
        rows = await UserChatRepository.filter(user_id=message.from_user.id)
        if rows:
            await UserChatRepository.update(rows[0].id, assistant_id=assistant.id, thread_id=thread.id)
        else:
            await UserChatRepository.add({
                "chat_id": message.chat.id,
                "user_id": message.from_user.id,
                "assistant_id": assistant.id,
                "thread_id": thread.id,
            })
    except IndexError:
        print("Пользователь не найден.")


@router.message(F.content_type == types.ContentType.TEXT)
@extract_info
async def message_handler(
        message: Message,
        assistant_id: str,
        thread_id: str
):
    await user_message(thread_id, message.text)
    reply_text = await run(assistant_id, thread_id)
    await message.answer(reply_text)


@router.message(F.content_type == types.ContentType.VOICE)
@extract_info
async def voice_handler(
        message: Message,
        bot: Bot,
        assistant_id: str,
        thread_id: str
):
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as input_voice:
        input_voice = input_voice.name
    try:
        voice_file = await bot.get_file(message.voice.file_id)
        voice_bytes = await bot.download_file(voice_file.file_path)
        with open(input_voice, "wb") as f:
            f.write(voice_bytes.read())
        with open(input_voice, "rb") as audio_file:
            transcription = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        await user_message(thread_id, transcription.text)
        reply_text = await run(assistant_id, thread_id)
        await message.answer(reply_text)

        response = await client.audio.speech.create(
            model="tts-1-hd",
            voice="onyx",
            input=reply_text
        )
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as output_voice:
            output_voice = output_voice.name

        with open(output_voice, "wb") as audio_file:
            audio_file.write(response.read())
        audio = FSInputFile(output_voice)
        await bot.send_audio(message.chat.id, audio)

    except PermissionDeniedError as e:
        print(f"Permission Denied Error: {e}")
        await message.answer("К сожалению, эта функция недоступна в вашем регионе.")
    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        try:
            await async_remove(input_voice)
        except FileNotFoundError:
            print(f"Файл {input_voice} не найден.")
        except UnboundLocalError:
            print("Переменная INPUT_VOICE не определена.")
        try:
            await async_remove(output_voice)
        except FileNotFoundError:
            print(f"Файл {output_voice} не найден.")
        except UnboundLocalError:
            print("Переменная OUTPUT_VOICE не определена.")


async def main():
    await create_table()
    bot = Bot(token=settings.TELEGRAM_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
