# Roadmap

## Milestone 1: Core Pipeline MVP

Цель: получить надежный конвейер приема Telegram-постов и публикации в VK/OK с базовой устойчивостью.

### Issue 1: Project runtime and config bootstrap

- Status: planned
- Priority: P0
- Goal: подготовить реальную runtime-структуру приложения, конфигурацию окружений и безопасную загрузку секретов
- Acceptance criteria:
  - есть конфиг для `dev` и `prod`
  - секреты читаются из env и не логируются
  - приложение стартует одной командой

### Issue 2: Persistent storage for source posts and delivery jobs

- Status: planned
- Priority: P0
- Goal: добавить постоянное хранилище для `source_posts`, `delivery_jobs`, `published_posts`, `audit_events`
- Acceptance criteria:
  - ingestion переживает рестарт процесса
  - статусы доставок сохраняются в БД
  - есть уникальные ограничения против дублей

### Issue 3: Telegram ingestion adapter

- Status: planned
- Priority: P0
- Goal: реализовать прием новых постов из Telegram и перевод в канонический формат
- Acceptance criteria:
  - принимаются новые посты одного канала
  - поддерживаются текст, одно изображение, несколько изображений
  - дубликаты одного сообщения не создают повторную запись

### Issue 4: Delivery queue and retry scheduler

- Status: planned
- Priority: P0
- Goal: ввести очередь доставки и bounded retry/backoff
- Acceptance criteria:
  - на каждый destination создается отдельная задача
  - transient errors уходят в retry
  - exhausted jobs получают `manual_review_required`

### Issue 5: VK publisher adapter

- Status: planned
- Priority: P0
- Goal: реализовать публикацию постов в сообщество VK
- Acceptance criteria:
  - текстовые посты публикуются
  - фото-посты публикуются
  - сохраняется `remote_post_id` или permalink

### Issue 6: Odnoklassniki publisher adapter

- Status: planned
- Priority: P0
- Goal: реализовать публикацию постов в Одноклассники
- Acceptance criteria:
  - текстовые посты публикуются
  - фото-посты публикуются
  - сохраняется идентификатор публикации на стороне OK

### Issue 7: Delivery status tracking and operator visibility

- Status: planned
- Priority: P0
- Goal: сделать наблюдаемыми статусы по каждой платформе
- Acceptance criteria:
  - видно `pending`, `published`, `failed`, `retry_scheduled`, `manual_review_required`
  - можно посмотреть последнюю ошибку
  - есть CLI или admin-команда для просмотра зависших задач

## Milestone 2: Operational Hardening

Цель: сделать систему пригодной для постоянной эксплуатации.

### Issue 8: Health checks and metrics

- Status: planned
- Priority: P1
- Goal: добавить health endpoint и базовые метрики
- Acceptance criteria:
  - есть `healthy/degraded/unhealthy`
  - есть счетчики success/error/retry
  - есть метрика глубины очереди

### Issue 9: Audit log for manual actions

- Status: planned
- Priority: P1
- Goal: логировать ручные действия оператора
- Acceptance criteria:
  - retry, disable destination, rotate token, remap target пишутся в audit log
  - фиксируются actor, action, target, result

### Issue 10: Backfill for missed Telegram posts

- Status: planned
- Priority: P1
- Goal: переобрабатывать пропущенный диапазон постов без дублей
- Acceptance criteria:
  - можно задать диапазон message ids
  - уже опубликованные записи не дублируются
  - результат backfill наблюдаем по задачам и логам

### Issue 11: Dead-letter flow and manual retry

- Status: planned
- Priority: P1
- Goal: оформить стабильный сценарий для задач, которые не получилось доставить автоматически
- Acceptance criteria:
  - exhausted jobs попадают в отдельный список
  - доступен ручной retry
  - неавторизованный оператор не может запускать retry

## Milestone 3: Threads Integration

Цель: подключить Threads безопасно и отдельно от основного контура.

### Issue 12: Threads API strategy validation

- Status: planned
- Priority: P1
- Goal: подтвердить допустимый способ автопубликации и зафиксировать контракт интеграции
- Acceptance criteria:
  - выбран официальный или приемлемый способ публикации
  - описаны ограничения по контенту и rate limits
  - есть решение по токенам и ротации

### Issue 13: Threads adapter behind feature flag

- Status: planned
- Priority: P1
- Goal: реализовать публикацию в Threads без риска для основного пайплайна
- Acceptance criteria:
  - адаптер включается feature flag
  - выключенный Threads не влияет на VK/OK
  - ошибки Threads не блокируют другие публикации

## Milestone 4: Content Quality and Scaling

Цель: улучшить качество контента и подготовить систему к росту.

### Issue 14: Platform-specific content rendering rules

- Status: planned
- Priority: P2
- Goal: сделать отдельные правила преобразования текста и медиа для каждой платформы
- Acceptance criteria:
  - есть лимиты длины текста по платформам
  - unsupported content классифицируется как permanent failure
  - форматирование обрабатывается предсказуемо

### Issue 15: Multiple source channels

- Status: planned
- Priority: P2
- Goal: поддержать больше одного Telegram-канала
- Acceptance criteria:
  - маршрутизация настраивается по source channel
  - дедупликация остается корректной
  - статусы не смешиваются между источниками

### Issue 16: Edit sync policy

- Status: planned
- Priority: P2
- Goal: определить и реализовать поведение при редактировании Telegram-постов
- Acceptance criteria:
  - выбрана политика `ignore` или `sync-text-only`
  - политика задокументирована
  - есть тесты на повторную обработку edits

## Suggested Issue Order

1. Issue 1
2. Issue 2
3. Issue 3
4. Issue 4
5. Issue 5
6. Issue 6
7. Issue 7
8. Issue 8
9. Issue 11
10. Issue 10
11. Issue 12
12. Issue 13
13. Issue 14
14. Issue 15
15. Issue 16
16. Issue 9

## Definition of Done for MVP

- Telegram ingestion работает на новых постах
- VK и OK публикуются независимо
- система не дублирует посты при повторной обработке
- retry/backoff и manual review работают
- статусы доставки видны оператору
- после рестарта состояние не теряется
- тесты проходят локально одной командой

