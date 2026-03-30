# Repost Bot

Python-проект для бота, который дублирует посты из Telegram в VK, Одноклассники и Threads.

## План работ

- [Roadmap](./ROADMAP.md)

## Текущий статус

- `Issue 1` из roadmap уже реализован
- `Issue 2` из roadmap уже реализован
- `Issue 3` частично реализован: есть Telegram update adapter
- `Issue 4` из roadmap реализован в baseline-варианте
- `Issue 5` из roadmap реализован в adapter-baseline варианте
- есть runtime-структура приложения
- есть конфиг `dev/prod`
- секреты читаются из env или `.env`
- маскировка секретов покрыта тестами
- есть SQLite-хранилище для `source_posts`, `delivery_jobs`, `published_posts`, `audit_events`
- ingestion и audit переживают рестарт процесса
- due `delivery_jobs` выбираются из persistent queue
- transient failures планируют retry, exhausted jobs получают `manual_review_required`
- есть отдельный `VkPublisher` с transport seam и интеграцией в worker

## Быстрый старт

1. Создай локальный `.env` на основе `.env.example`
2. Заполни токены и target ids
3. Запусти приложение:

```bash
python3 -m repost_bot
```

Команда выведет masked summary текущей конфигурации и проверит, что обязательные переменные окружения заданы.
При первом запуске также будет создан локальный SQLite-файл по пути из `DATABASE_PATH`.

## Запуск тестов

```bash
python3 -m unittest discover -s tests -v
```

## Конфигурация

- `APP_ENV`: `dev` или `prod`
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `TELEGRAM_CHANNEL_ID`
- `TELEGRAM_BOT_TOKEN`
- `VK_COMMUNITY_ID`
- `VK_ACCESS_TOKEN`
- `OK_GROUP_ID`
- `OK_ACCESS_TOKEN`
- `THREADS_ACCOUNT_ID`
- `THREADS_ACCESS_TOKEN`
- `ALLOWED_OPERATORS`: список через запятую

## Telegram ingestion

В проекте уже есть [telegram_adapter.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/telegram_adapter.py), который умеет:

- принимать `channel_post` update payload
- фильтровать апдейты не из целевого канала
- извлекать текст, caption, photo и `media_group_id`
- отбрасывать unsupported или пустые channel posts

## Delivery queue

В проекте уже есть persisted queue semantics на базе [storage.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/storage.py) и [service.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/service.py):

- создаются `delivery_jobs` по destination
- `DeliveryWorker.process_due_jobs()` берет только due jobs
- успешные публикации пишут `published_posts`
- transient failures уходят в `retry_scheduled`
- exhausted retries переводятся в `manual_review_required`

## VK adapter

В проекте уже есть [vk_adapter.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/vk_adapter.py):

- `VkPublisher` принимает `PlatformCredentials`
- публикация идет через отдельный transport seam
- worker умеет использовать VK adapter для `vk-destination`
- успешная публикация сохраняет `remote_post_id` в `published_posts`
- transient VK errors переводятся в `retry_scheduled`
