import base64
import openai
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from contextlib import contextmanager
from psycopg2 import connect, OperationalError


TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN') or exit("🚨Error: TELEGRAM_TOKEN is not set.")
openai.api_key = os.getenv('OPENAI_API_KEY') or None
DATABASE_URL = os.getenv('DATABASE_PRIVATE_URL') or exit("🚨Error: DB_URL is not set.")
client = openai.OpenAI()


@contextmanager
def get_db_connection():
    connection = None
    try:
        connection = connect(DATABASE_URL)
        # print("\nСоединение с БД установлено", connection, "\n")
        yield connection
    except OperationalError as e:
        print('БД не доступна', e)
    finally:
        if connection:
            connection.close()


@contextmanager
def get_db_cursor(connection):
    cursor = None
    try:
        cursor = connection.cursor()
        yield cursor
    except Exception as e:
        print("Ошибка при выполнении запроса:", e)
    finally:
        if cursor:
            cursor.close()

def create_database():

    with get_db_connection() as connection:
        if connection:
            with get_db_cursor(connection) as cursor:
                if cursor:
                    cursor.execute(
                '''CREATE TABLE IF NOT EXISTS messages (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        role_user VARCHAR(50) NOT NULL,
                        message TEXT NOT NULL,
                        date_message TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''
            )
            connection.commit()


def save_message(user_id, chat_id, role_user, message):

    with get_db_connection() as connection:
        if connection:
            with get_db_cursor(connection) as cursor:
                if cursor:
                    cursor.execute(
                        'INSERT INTO messages (user_id, chat_id, role_user, message) VALUES (%s, %s, %s, %s)',
                        (user_id, chat_id, role_user, message)
            )
            connection.commit()


def get_message_history(chat_id, limit=4096):

    with get_db_connection() as connection:
        if connection:
            with get_db_cursor(connection) as cursor:
                if cursor:
                    cursor.execute(
                        'SELECT role_user, message FROM messages WHERE chat_id = %s ORDER BY date_message LIMIT %s',
                        (chat_id, limit)
                    )
                    rows = cursor.fetchall()

    history = ([{"role": "system",
                 "content": "Ты полезный помощник. Говори по русски, но в русских словах добавляй белорусские окончания. Можешь задавть вопросы по одному"
                 }] +
            [{"role": row[0], "content": row[1]} for row in rows[1:]])
    return history


def get_session_id(func):
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        session_id = str(update.effective_chat.id if update.effective_chat.type in ['group', 'supergroup'] else update.effective_user.id)
        user_id = str(update.effective_user.id)
        role_user = "user"
        message = update.message.text
        save_message(user_id, session_id, role_user, message)

        user_first_name = update.effective_user.first_name
        user_last_name = update.effective_user.last_name
        full_name = f"{user_first_name} {user_last_name}" if user_last_name else user_first_name
        return await func(update, context, session_id, user_id, full_name, *args, **kwargs)
    return wrapper


# Обработчик команды /start
@get_session_id
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: str, user_id, full_name: str) -> None:
    await update.message.reply_text(f'Привет, {full_name}. Я - помощник во всем. Присылайте текст, голос или картинку.')


def text_generate(msg):
    response = client.chat.completions.create(model="gpt-4o", messages=msg)
    return response


# Обработчик текстовых сообщений
@get_session_id
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: str, user_id, full_name: str) -> None:
    history = get_message_history(session_id)
    reply_text = text_generate(history).choices[0].message.content
    role_user = "assistant"
    save_message(user_id, session_id, role_user, reply_text)
    await update.message.reply_text(f"{full_name}, {reply_text}")


# # Обработчик голосовых сообщений
@get_session_id
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: str, user_id, full_name: str) -> None:

    # Получение файла голосового сообщения
    audio_file = await update.message.voice.get_file()
    voice = await audio_file.download_as_bytearray()
    with open('output.ogg', "wb") as f:
        f.write(voice)
    audio_file = open("output.ogg", "rb")

    # Преобразование голосового запроса в текст
    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file
    )

    # Добавление сообщения в историю
    user_role = "user"
    save_message(user_id, session_id, user_role, transcription.text)

    # Генерация ответа
    history = get_message_history(session_id)
    reply_text = text_generate(history).choices[0].message.content

    # Добавление ответа  в историю
    user_role = "assistant"
    save_message(user_id, session_id, user_role, reply_text)

    # transform reply_text to file mp3
    response = client.audio.speech.create(
        model="tts-1-hd",
        voice="onyx",
        input=reply_text
    )

    # Сохранение голосового ответа в файл
    response.stream_to_file("speech.mp3")

    # Отправка голосового ответа
    await update.message.reply_voice(voice=open("speech.mp3", 'rb'))


# Обработчик изображений
@get_session_id
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: str, user_id, full_name: str) -> None:

    # Получение файла изображений
    photo = update.message.photo[-1]
    file = await photo.get_file()
    await file.download_to_drive("image.jpg")

    # Передача файла изображения в модель для распознавания
    with open("image.jpg", "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Что изображено на картинке? Предложи тему научной работы и ее проблематику, связанной с содержанием картинки."},
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

    # response to user text
    reply_text = response.choices[0].message.content
    await update.message.reply_text(f"{reply_text}")

    # Добавление сообщения в историю
    user_role = "user"
    save_message(user_id, session_id, user_role, reply_text)


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
    create_database()

    main()
