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
- `Issue 12/13` реализованы в Threads strategy + feature-flag baseline варианте
- `Issue 14` из roadmap реализован в baseline-варианте platform rendering rules
- `Issue 16` из roadmap реализован в baseline-варианте edit sync policy
- `Issue 15` из roadmap реализован в baseline-варианте multiple source channels
- `Issue 9` из roadmap реализован в baseline-варианте audit log for manual actions
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
- есть Threads adapter под feature flag
- есть platform-specific baseline rules для VK, OK и Threads
- есть baseline policy для Telegram edits: `edited_channel_post` распознается, но не репаблишится автоматически
- есть baseline support для нескольких исходных Telegram-каналов
- есть audit log для ручных операторских действий
- есть реальный Telegram long-polling loop для live ingestion
- есть real HTTP text-post path для VK и Threads
- для OK зафиксировано официальное ограничение: baseline использует manual/widget-oriented flow, а не server-side autopost
- VK теперь умеет live photo upload path через Telegram file download + VK wall photo upload

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
python3 -m repost_bot disable-destination --database var/repost-bot.sqlite3 --destination-id ok-destination --actor allowed-operator
python3 -m repost_bot remap-target --database var/repost-bot.sqlite3 --destination-id vk-destination --target-id vk-community-77 --actor allowed-operator
python3 -m repost_bot rotate-token --database var/repost-bot.sqlite3 --config-ref vk-config --actor allowed-operator
python3 -m repost_bot audit-log --database var/repost-bot.sqlite3 --limit 20
```

Для backfill диапазона:

```bash
python3 -m repost_bot backfill --database var/repost-bot.sqlite3 --start-message-id 300 --end-message-id 320 --actor allowed-operator
python3 -m repost_bot backfill --database var/repost-bot.sqlite3 --start-message-id 300 --end-message-id 320 --channel-id tg-channel-2 --actor allowed-operator
```

Для включения Threads:

```bash
THREADS_ENABLED=true python3 -m repost_bot
```

Для запуска live polling loop:

```bash
python3 -m repost_bot run-poller --once
python3 -m repost_bot run-poller
```

## Запуск тестов

```bash
python3 -m unittest discover -s tests -v
```

## Конфигурация

- `APP_ENV`: `dev` или `prod`
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `TELEGRAM_CHANNEL_ID`
- `TELEGRAM_CHANNEL_IDS`: опциональный список source channel ids через запятую для multi-channel режима
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_POLL_TIMEOUT_SECONDS`
- `TELEGRAM_POLL_INTERVAL_SECONDS`
- `DELIVERY_BATCH_LIMIT`
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
- принимать `edited_channel_post` update payload
- фильтровать апдейты не из целевого канала
- фильтровать апдейты по одному или нескольким разрешенным source channels
- извлекать текст, caption, photo и `media_group_id`
- отбрасывать unsupported или пустые channel posts
- помечать edit events и передавать их дальше как `is_edit`

Live polling loop находится в [telegram_poller.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/telegram_poller.py):

- ходит в Telegram Bot API через `getUpdates`
- держит `offset` между polling-итерациями
- после ingestion запускает обработку due `delivery_jobs`
- поддерживает `run_once()` и `run_forever()`

## Multiple Source Channels

Текущий baseline для multi-channel режима:

- можно использовать один `TELEGRAM_CHANNEL_ID` как раньше
- или включить несколько каналов через `TELEGRAM_CHANNEL_IDS=channel-a,channel-b`
- adapter принимает updates из любого разрешенного source channel
- ingestion и дедупликация остаются привязанными к паре `source_channel_id + message_id`

## Edit Sync Policy

Текущий baseline для edits:

- `edited_channel_post` распознается на уровне Telegram adapter
- автоматический republish правок выключен
- edit events возвращают `edit_ignored` и не создают новые `source_posts` или `delivery_jobs`
- это защищает pipeline от дублей и неявного рассинхрона между платформами, пока не реализована полноценная sync-стратегия

## Delivery queue

В проекте уже есть persisted queue semantics на базе [storage.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/storage.py) и [service.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/service.py):

- создаются `delivery_jobs` по destination
- `DeliveryWorker.process_due_jobs()` берет только due jobs
- успешные публикации пишут `published_posts`
- transient failures уходят в `retry_scheduled`
- exhausted retries переводятся в `manual_review_required`

## Live Outbound Publishing

Текущий production baseline по outbound:

- [vk_adapter.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/vk_adapter.py) умеет реальный HTTP `wall.post` path для текстовых постов
- VK photo posts теперь проходят через Telegram file download, `photos.getWallUploadServer`, upload и `photos.saveWallPhoto`
- [threads_adapter.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/threads_adapter.py) умеет реальный HTTP create/publish path для текстовых постов
- [ok_adapter.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/ok_adapter.py) по умолчанию возвращает явную permanent error, потому что в текущем baseline не настроен официальный интерактивный group publishing flow
- Для live VK API `VK_COMMUNITY_ID` должен быть numeric community id
- Threads media и OK autopost пока не доведены до production upload flow

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

## Audit Log

Audit baseline теперь покрывает:

- `retry_delivery_job`
- `disable_destination`
- `remap_target`
- `rotate_token`

Для `rotate-token` в audit log пишется только безопасный факт ротации без хранения нового секрета.

CLI-доступ:

- `python3 -m repost_bot disable-destination --destination-id ... --actor ...`
- `python3 -m repost_bot remap-target --destination-id ... --target-id ... --actor ...`
- `python3 -m repost_bot rotate-token --config-ref ... --actor ...`
- `python3 -m repost_bot audit-log`

## Backfill

Backfill baseline покрывает:

- обработку диапазона `message_id`
- выбор source channel через `--channel-id` или дефолтный канал из конфига
- создание только недостающих `source_posts`
- отсутствие дублей по уже обработанным постам
- автоматическое создание `delivery_jobs` для новых backfill-записей

CLI-доступ:

- `python3 -m repost_bot backfill --start-message-id ... --end-message-id ... --actor ...`

## Threads

- strategy note: [docs/threads-strategy.md](/Users/innokentyb/Documents/Repost%20bot/docs/threads-strategy.md)
- `ThreadsPublisher` живет в [threads_adapter.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/threads_adapter.py)
- по умолчанию `THREADS_ENABLED=false`
- при включении flag `threads-destination` становится `active`
- при выключенном flag Threads не участвует в основном pipeline

## Platform Rendering Rules

Текущий baseline в [rendering.py](/Users/innokentyb/Documents/Repost%20bot/repost_bot/rendering.py):

- текст нормализуется по пробелам
- `VK`: допускает `photo` и `video`
- `OK`: baseline допускает только `photo`
- `Threads`: baseline допускает только текст или одну `photo`
- `poll` и unsupported media классифицируются как `content_not_supported`

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
