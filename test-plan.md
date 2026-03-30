# TDD test plan для бота репоста из Telegram в VK, Одноклассники и Threads

## 1. Feature model

Система принимает новые посты из одного Telegram-канала, сохраняет их в каноническом виде и создает независимые задачи доставки в VK, Одноклассники и Threads. Для каждой платформы состояние доставки наблюдаемо отдельно. Повторная доставка одного и того же Telegram-поста в одну и ту же платформу без явного override недопустима.

Основные акторы и зависимости:

- Telegram как источник входящих событий
- сервис репоста как orchestrator
- адаптеры VK, OK и Threads как внешние зависимости
- оператор/администратор как пользователь ручных действий

Бизнес-правила, которые нужно закрепить тестами до реализации:

- один Telegram-пост превращается в один `source_post`
- для каждой активной destination создается отдельная задача доставки
- отказ одной платформы не ломает доставку в другие
- повторная обработка того же события не создает дубли публикаций
- при исчерпании retry задача переводится в `manual_review_required`
- отключенная платформа не получает новые задачи публикации

Принятые допущения для тест-плана:

- MVP покрывает текст, одно изображение и несколько изображений
- удаление постов из Telegram не синхронизируется
- edit-sync в MVP выключен
- Threads идет под feature flag и может быть отключен полностью
- у системы есть наблюдаемые артефакты: записи в БД, статусы delivery jobs, remote post ids, audit events и метрики/события ошибок

## 2. Testability assessment

- Требование "дублирует все посты" пока недостаточно точное: не определено, какие именно типы Telegram-сообщений считаются поддерживаемыми для MVP.
- Не зафиксировано, что является входом системы: webhook, polling или client API. Для TDD это влияет на контракт ingestion-теста, но не мешает планировать service-level tests.
- Не определено, как именно система должна вести себя при "неясном успехе", когда внешняя платформа могла создать пост, но ответ потерялся. Нужен наблюдаемый контракт reconcilation.
- Не определено, как нормализуется форматирование Telegram в каждой платформе. Без этого часть content-rendering тестов будет нестабильной.
- Не определены лимиты текста и медиа по платформам как явная таблица правил. Без этого boundary-тесты не до конца формализуемы.
- Не определено, как именно выглядит ручной override и кто имеет право его запускать. Это блокирует часть тестов на admin actions.
- Нефункциональные требования про метрики и health checks сформулированы достаточно, но не зафиксированы точные имена метрик и коды состояний.
- Threads отмечен как условная интеграция. Это TDD-ready только если тесты явно различают режим `feature flag off` и `feature flag on`.

Итог: требования частично TDD-ready. Ядро сервиса, дедупликацию, статусы, retries и частичные сбои можно тестировать сразу. Контентные границы, edit behavior и часть admin semantics требуют уточнений.

## 3. Test scenarios

### Сценарии первого цикла red-green-refactor

#### Scenario 1

- Priority: must-have
- Level: service
- Title: Новый Telegram-пост создает одну исходную запись и задачи доставки для всех активных платформ
- Preconditions: настроен один источник Telegram; активны destinations `vk`, `ok`, `threads`; входящий пост валиден и содержит текст
- Action: сервис обрабатывает событие нового Telegram-поста
- Expected result: создается один `source_post`; создаются три `delivery_job` со статусом `pending`; текст сохраняется в `raw_payload` и `normalized_payload`
- Notes on edge case or failure mode: это базовый контракт orchestration, от него зависят почти все остальные тесты

#### Scenario 2

- Priority: must-have
- Level: service
- Title: Повторная доставка того же Telegram-события не создает дубль source_post и delivery_jobs
- Preconditions: пост с тем же `telegram_chat_id + telegram_message_id` уже был успешно принят
- Action: сервис повторно получает тот же Telegram-пост
- Expected result: не создается второй `source_post`; не создаются новые delivery jobs; возвращается наблюдаемый результат "duplicate ignored" или эквивалентный статус
- Notes on edge case or failure mode: ключевой тест на идемпотентность ingestion

#### Scenario 3

- Priority: must-have
- Level: integration
- Title: Успешная публикация в одной платформе фиксирует remote post id и меняет только ее статус
- Preconditions: существует `delivery_job` для VK в статусе `pending`; mock VK API отвечает успехом
- Action: воркер обрабатывает задачу доставки
- Expected result: у VK-задачи статус `published`; создается `published_post` с `remote_post_id`; статусы OK и Threads не изменяются
- Notes on edge case or failure mode: проверяет независимость статусов по платформам

#### Scenario 4

- Priority: must-have
- Level: integration
- Title: Ошибка одной платформы не мешает успешной публикации в остальные
- Preconditions: для одного `source_post` есть три задачи доставки; VK отвечает 200, OK отвечает 500, Threads отвечает 200
- Action: воркер обрабатывает все три задачи
- Expected result: VK и Threads переходят в `published`; OK переходит в `retry_scheduled` или `failed` согласно policy; агрегированное состояние поста отражает частичный успех
- Notes on edge case or failure mode: главный тест на partial failure

#### Scenario 5

- Priority: must-have
- Level: integration
- Title: Timeout внешнего API переводит задачу в retry_scheduled с увеличением attempt_count
- Preconditions: `delivery_job` в статусе `pending`; адаптер платформы возвращает timeout; policy retry включена
- Action: воркер пытается опубликовать пост
- Expected result: `attempt_count` увеличен на 1; задача переведена в `retry_scheduled`; `next_attempt_at` установлен в будущем; ошибка классифицирована как transient
- Notes on edge case or failure mode: нужен для bounded retries и backoff

#### Scenario 6

- Priority: must-have
- Level: integration
- Title: После исчерпания лимита retry задача уходит в manual_review_required
- Preconditions: задача уже достигла максимального числа retry; следующий вызов снова завершится transient error
- Action: воркер повторно обрабатывает задачу
- Expected result: статус становится `manual_review_required`; дальнейшие автоматические retry не планируются; причина ошибки сохранена
- Notes on edge case or failure mode: этот сценарий нужен для dead-letter semantics

#### Scenario 7

- Priority: must-have
- Level: service
- Title: Отключенная платформа не получает новых delivery jobs
- Preconditions: `vk` и `ok` активны, `threads` имеет статус `disabled`
- Action: сервис принимает новый Telegram-пост
- Expected result: создаются задачи только для VK и OK; для Threads задача не создается
- Notes on edge case or failure mode: фиксирует требование "можно выключить отдельную платформу"

#### Scenario 8

- Priority: must-have
- Level: integration
- Title: Повторная обработка delivery job после успешной публикации не создает второй remote post
- Preconditions: задача уже имеет статус `published` и связанный `remote_post_id`
- Action: воркер случайно повторно получает ту же задачу
- Expected result: внешний publish не вызывается повторно или безопасно short-circuit'ится; второй `published_post` не создается
- Notes on edge case or failure mode: тест на идемпотентность уже на уровне публикации

### Сценарии устойчивости и бизнес-правил

#### Scenario 9

- Priority: should-have
- Level: unit
- Title: Нормализатор поста корректно преобразует текстовый Telegram-пост в канонический формат
- Preconditions: входной Telegram payload содержит текст, ссылки и базовое форматирование
- Action: вызвать normalizer
- Expected result: возвращается канонический объект поста с предсказуемыми полями; неподдерживаемые детали форматирования либо отбрасываются, либо помечаются явно
- Notes on edge case or failure mode: важен для последующих renderer tests

#### Scenario 10

- Priority: should-have
- Level: unit
- Title: Нормализатор корректно собирает пост с несколькими изображениями
- Preconditions: входной Telegram payload содержит media group
- Action: вызвать normalizer
- Expected result: в каноническом формате появляется один пост с упорядоченным списком изображений, а не несколько независимых постов
- Notes on edge case or failure mode: критично для альбомов и дедупликации

#### Scenario 11

- Priority: should-have
- Level: unit
- Title: Renderer платформы отклоняет контент, который не поддерживается целевой платформой
- Preconditions: канонический пост содержит unsupported media type или слишком длинный текст для платформы
- Action: вызвать platform renderer
- Expected result: возвращается валидируемая ошибка `content_not_supported` или эквивалент; delivery job не уходит в бесконечный retry
- Notes on edge case or failure mode: разделяет permanent failure и transient failure

#### Scenario 12

- Priority: should-have
- Level: integration
- Title: Rate limit от внешней платформы уважает рекомендованную задержку
- Preconditions: publish API возвращает ответ rate-limited с retry-after
- Action: воркер обрабатывает задачу публикации
- Expected result: задача переводится в `retry_scheduled`; `next_attempt_at` рассчитывается не раньше рекомендованной задержки
- Notes on edge case or failure mode: защищает от каскадных повторов и банов

#### Scenario 13

- Priority: should-have
- Level: integration
- Title: Перезапуск сервиса не теряет незавершенные задачи доставки
- Preconditions: есть задача в статусе `pending` или `retry_scheduled`; процесс сервиса остановлен до завершения публикации
- Action: сервис стартует заново и поднимает обработку
- Expected result: незавершенная задача остается в консистентном состоянии и позже дообрабатывается без создания дублей
- Notes on edge case or failure mode: обязательный resilience-сценарий перед продом

#### Scenario 14

- Priority: should-have
- Level: service
- Title: Неясный исход публикации сначала запускает reconciliation, а не слепой повтор
- Preconditions: внешний API не вернул подтверждение, но исход операции неизвестен
- Action: сервис обрабатывает результат публикации
- Expected result: задача переходит в состояние проверки или выполняет lookup существующего remote post; повторная отправка не выполняется до завершения reconciliation
- Notes on edge case or failure mode: предотвращает дубли после network split

#### Scenario 15

- Priority: should-have
- Level: service
- Title: Ошибка валидации входящего Telegram-события блокирует создание source_post
- Preconditions: входной payload пустой, malformed или превышает допустимый размер
- Action: сервис принимает событие
- Expected result: запись `source_post` не создается; ошибка классифицируется как validation failure; формируется наблюдаемый reject outcome
- Notes on edge case or failure mode: тестирует входную границу доверия

#### Scenario 16

- Priority: should-have
- Level: integration
- Title: Ручной retry доступен только разрешенному оператору и аудируется
- Preconditions: задача находится в `manual_review_required`; есть авторизованный и неавторизованный оператор
- Action: оба пытаются запустить retry
- Expected result: разрешенный оператор инициирует новую попытку и пишет `audit_event`; неразрешенный получает отказ и не меняет состояние задачи
- Notes on edge case or failure mode: закрепляет permission boundary

### Сценарии второй волны покрытия

#### Scenario 17

- Priority: should-have
- Level: API
- Title: Health endpoint отражает деградацию очереди или недоступность критической зависимости
- Preconditions: очередь переполнена или недоступна БД
- Action: вызвать health endpoint
- Expected result: ответ показывает degraded/unhealthy статус по задокументированному контракту
- Notes on edge case or failure mode: нужен для эксплуатации, но не блокирует первый red-green цикл

#### Scenario 18

- Priority: should-have
- Level: integration
- Title: Backfill диапазона постов создает только недостающие доставки без дублей
- Preconditions: часть постов уже обработана, часть пропущена
- Action: оператор запускает backfill по диапазону Telegram message ids
- Expected result: ранее опубликованные посты не дублируются; создаются задачи только для реально пропущенных исходных постов
- Notes on edge case or failure mode: связан с recovery после простоя

#### Scenario 19

- Priority: nice-to-have
- Level: unit
- Title: Логи и ошибки не содержат секретов
- Preconditions: адаптер получает ошибку, содержащую токен или чувствительные заголовки
- Action: система пишет лог ошибки
- Expected result: чувствительные значения замаскированы или удалены
- Notes on edge case or failure mode: это security regression test, особенно полезен после появления реальных интеграций

#### Scenario 20

- Priority: nice-to-have
- Level: integration
- Title: Threads feature flag off полностью исключает эту платформу из конвейера
- Preconditions: destination Threads настроен, но feature flag выключен
- Action: сервис обрабатывает новый Telegram-пост
- Expected result: задачи для Threads не создаются или сразу маркируются как skipped по задокументированному контракту; VK и OK продолжают работу
- Notes on edge case or failure mode: фиксирует безопасное отключение нестабильной интеграции

#### Scenario 21

- Priority: nice-to-have
- Level: integration
- Title: Telegram-события вне порядка не ломают итоговый статус ранее принятого поста
- Preconditions: система уже обработала message id `101`; позже приходит задержавшееся событие, относящееся к более раннему или дублирующему контексту
- Action: обработать out-of-order event
- Expected result: ранее зафиксированные публикации не перетираются; новые ложные задачи не создаются
- Notes on edge case or failure mode: особенно важно при polling/client API

#### Scenario 22

- Priority: nice-to-have
- Level: integration
- Title: Метрики публикаций увеличиваются только по фактически завершенным исходам
- Preconditions: один publish success, один timeout with retry, один permanent validation failure
- Action: обработать все три исхода
- Expected result: success/error/retry metrics отражают фактические исходы без двойного учета
- Notes on edge case or failure mode: предотвращает ложную observability

## 4. Corner cases and failure paths

- Повторная доставка одного и того же Telegram-поста после рестарта сервиса.
- Успешная публикация на внешней платформе при потере ответа от API.
- Частичный успех: одна или две платформы опубликовали, остальные ушли в retry.
- Media group приходит несколькими событиями и может ошибочно раздробиться на несколько постов.
- Контент валиден для Telegram, но невалиден для VK/OK/Threads.
- Rate limit одной платформы приводит к накапливанию очереди и не должен блокировать другие направления.
- Ручной retry без прав оператора не должен менять состояние и должен быть наблюдаемо отклонен.
- Повторная обработка уже `published` delivery job не должна порождать новый пост во внешней системе.

## 5. Open questions

- Какой точный контракт ingestion на MVP: webhook, polling или client API?
- Какие типы Telegram-контента считаются поддерживаемыми в первом релизе, кроме текста и изображений?
- Какой наблюдаемый результат должен быть у повторного приема дубликата: silent no-op, специальный статус или audit event?
- Что считается "неясным успехом" и каким способом система должна выполнять reconciliation для каждой платформы?
- Как выглядит политика retry: максимальное число попыток, базовая задержка, upper bound, jitter?
- Какой именно статус должен получать permanently unsupported content: `failed` или сразу `manual_review_required`?
- Нужен ли единый агрегированный статус у source post, и если да, какие правила вычисления?
- Какой контракт у ручного retry: создает новую job или реиспользует существующую?
- Кто считается разрешенным оператором и через какой интерфейс выполняются административные действия?
- Как именно Threads должен вести себя при выключенном feature flag: не создавать job или создавать `skipped`?
- Нужно ли в MVP проверять маскирование секретов автоматическими тестами или это останется policy-level check?
- Требуется ли backfill в первом релизе или это отдельный этап после запуска базового конвейера?

