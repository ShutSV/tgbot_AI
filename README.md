# tgbot_AI

A simple Telegram Chatbot using OpenAI GPT models
---

Телеграм-бот на библиотеке aiogram, который способен принимать голосовые сообщения, преобразовывать их в текст, получать ответы на заданные вопросы и озвучивать ответы обратно пользователю с использованием асинхронного клиента OpenAI API.

Используется OpenAI Assistant API (не Completions API) для получения ответов на вопросы. Все запросы идут через асинхронный клиент OpenAI в их SDK

Подключена база данных PostgreSQL для хранения информации о потоке. Для работы с БД используется асинхронная версия SQLAlchemy ORM
Бот и БД запускаются через контейнеры Docker

Используются модели:
- обработка текста и изображений - gpt-4o
- распознавание голоса - whisper-1 для конвертации голосового сообщения в текст. 
- преобразование текста в аудио - tts-1-hd для озвучки полученных ответов

