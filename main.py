import base64
import openai
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters


TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN') or exit("🚨Error: TELEGRAM_TOKEN is not set.")
openai.api_key = os.getenv('OPENAI_API_KEY') or None
client = openai.OpenAI()


def text_generate(msg):
    messages = [
        {"role": "system", "content": "You are a useful assistant - nutritiotist."},
        {"role": "user", "content": msg + "Ответь на белорусском языке"},
    ]
    return client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )


# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_first_name = update.effective_user.first_name
    await update.message.reply_text(f'{user_first_name}, отправьте текст, голос, или изображение.')


# Обработчик текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_first_name = update.effective_user.first_name
    response = text_generate(update.message.text)
    reply_text = response.choices[0].message.content
    await update.message.reply_text(f"{user_first_name}, {reply_text}")


# # Обработчик голосовых сообщений
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    # Получение файла голосового сообщения
    audio_file = await update.message.voice.get_file()
    voice = await audio_file.download_as_bytearray()
    with open('output.ogg', "wb") as f:
        f.write(voice)
    audio_file = open("output.ogg", "rb")

    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file
    )

    await update.message.reply_text(f"""user: "{transcription.text}""""")

    response = text_generate(transcription.text)
    reply_text = response.choices[0].message.content
    await update.message.reply_text(f"{reply_text}")

    # transform reply_text to file mp3
    response = client.audio.speech.create(
        model="tts-1-hd",
        voice="onyx",
        input=reply_text
    )
    response.stream_to_file("speech.mp3")

    # Отправляем голосовой ответ
    await update.message.reply_voice(voice=open("speech.mp3", 'rb'))


# Обработчик изображений
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    photo = update.message.photo[-1]
    file = await photo.get_file()
    await file.download_to_drive("image.jpg")

    with open("image.jpg", "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Что на этой картинке, сколько примерно весит каждый человек, какой он комплекции, и ответь на белорусском языке?"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    },
                ],
            }
        ],
        max_tokens=300,
    )

    # response to user
    print("ответ AI:", response.choices[0].message.content)
    reply_text = response.choices[0].message.content
    await update.message.reply_text(f"AI: {reply_text}")

    # transform reply_text to file mp3
    response = client.audio.speech.create(
        model="tts-1-hd",
        voice="onyx",
        input=reply_text
    )
    response.stream_to_file("speech.mp3")

    # Отправляем голосовой ответ
    await update.message.reply_voice(voice=open("speech.mp3", 'rb'))


def main():

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)  # Увеличение времени ожидания подключения
        .read_timeout(30)  # Увеличение времени ожидания чтения ответа
        .write_timeout(30)  # Увеличение времени ожидания записи запроса
        .pool_timeout(10)  # Увеличение времени ожидания получения соединения из пула
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    application.run_polling()


if __name__ == "__main__":

    main()
