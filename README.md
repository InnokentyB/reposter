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
- `Issue 6` из roadmap реализован в adapter-baseline варианте
- `Issue 7` из roadmap реализован в CLI-baseline варианте
- `Issue 8` из roadmap реализован в health/metrics baseline варианте
- `Issue 11` из roadmap реализован в dead-letter/manual-retry baseline варианте
- `Issue 10` из roadmap реализован в backfill baseline варианте
- есть runtime-структура приложения
- есть конфиг `dev/prod`
- секреты читаются из env или `.env`
- маскировка секретов покрыта тестами
- есть SQLite-хранилище для `source_posts`, `delivery_jobs`, `published_posts`, `audit_events`
- ingestion и audit переживают рестарт процесса
- due `delivery_jobs` выбираются из persistent queue
- transient failures планируют retry, exhausted jobs получают `manual_review_required`
- есть отдельный `VkPublisher` с transport seam и интеграцией в worker
- есть отдельный `OkPublisher` с transport seam и интеграцией в worker
- есть CLI-команда для просмотра статусов, зависших задач и последних ошибок
- есть health-команда и реальные метрики на основе состояния БД и очереди
- есть dead-letter очередь и ручной retry для `manual_review_required`
- есть backfill диапазона `message_id` без дублей

## Быстрый старт

1. Создай локальный `.env` на основе `.env.example`
2. Заполни токены и target ids
3. Запусти приложение:

```bash
python3 -m repost_bot
```

Команда выведет masked summary текущей конфигурации и проверит, что обязательные переменные окружения заданы.
При первом запуске также будет создан локальный SQLite-файл по пути из `DATABASE_PATH`.

Для просмотра текущего состояния доставок:

```bash
python3 -m repost_bot status --database var/repost-bot.sqlite3 --limit 20
```

Для health и метрик:

```bash
python3 -m repost_bot health --database var/repost-bot.sqlite3
```

Для dead-letter и ручного retry:

```bash
python3 -m repost_bot dead-letter --database var/repost-bot.sqlite3 --limit 20
python3 -m repost_bot retry-job --database var/repost-bot.sqlite3 --job-id source-123:ok-destination --actor allowed-operator
```

Для backfill диапазона:

```bash
python3 -m repost_bot backfill --database var/repost-bot.sqlite3 --start-message-id 300 --end-message-id 320 --actor allowed-operator
```

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

## Admin CLI

В проекте уже есть [admin_cli.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/admin_cli.py):

- summary по числу `delivery_jobs` в каждом статусе
- список stuck/due jobs
- список последних ошибок доставки
- запуск через `python3 -m repost_bot status`

## Health And Metrics

`HealthService` теперь считает состояние по реальным данным:

- `database: healthy/unhealthy`
- `queue: healthy/degraded`
- `success_count`
- `error_count`
- `retry_count`
- `queue_depth`

CLI-доступ:

- `python3 -m repost_bot health`

## Dead-Letter And Manual Retry

Dead-letter flow теперь покрывает:

- отдельный список задач в `manual_review_required`
- ручной retry только для разрешенного оператора
- возврат задачи в `pending`
- очистку ошибки и счетчика попыток
- audit event на ручной retry

CLI-доступ:

- `python3 -m repost_bot dead-letter`
- `python3 -m repost_bot retry-job --job-id ... --actor ...`

## Backfill

Backfill baseline покрывает:

- обработку диапазона `message_id`
- создание только недостающих `source_posts`
- отсутствие дублей по уже обработанным постам
- автоматическое создание `delivery_jobs` для новых backfill-записей

CLI-доступ:

- `python3 -m repost_bot backfill --start-message-id ... --end-message-id ... --actor ...`

## VK adapter

В проекте уже есть [vk_adapter.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/vk_adapter.py):

- `VkPublisher` принимает `PlatformCredentials`
- публикация идет через отдельный transport seam
- worker умеет использовать VK adapter для `vk-destination`
- успешная публикация сохраняет `remote_post_id` в `published_posts`
- transient VK errors переводятся в `retry_scheduled`

## OK adapter

В проекте уже есть [ok_adapter.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/ok_adapter.py):

- `OkPublisher` принимает `PlatformCredentials`
- публикация идет через отдельный transport seam
- worker умеет использовать OK adapter для `ok-destination`
- успешная публикация сохраняет `remote_post_id` в `published_posts`
- transient OK errors переводятся в `retry_scheduled`
- permanent OK errors переводятся в `failed`
