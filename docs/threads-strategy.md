# Threads Strategy

## Decision

Threads интеграция в этом проекте должна идти только через официальный Meta Threads API и оставаться под feature flag до отдельного production-подтверждения.

## Why

- Официальный Postman workspace Meta прямо позиционирует себя как официальный вход в Threads API landscape и ссылается на developer docs:
  [Meta Threads official Postman workspace](https://www.postman.com/meta/threads/overview)
- Официальный sample app от Meta для Threads API указывает на developer docs, changelog и отдельные требования к app credentials и redirect URLs:
  [fbsamples/threads_api](https://github.com/fbsamples/threads_api)

## Constraints We Will Respect

- Не использовать reverse-engineered или unofficial clients в production-контуре.
- Не делать Threads обязательной частью основного pipeline.
- Держать `THREADS_ENABLED=false` значением по умолчанию.
- Любые ошибки Threads не должны блокировать VK/OK delivery path.

## Current Implementation Baseline

- В проекте есть `ThreadsPublisher` с transport seam.
- Активация `threads-destination` зависит от `THREADS_ENABLED`.
- Worker использует отдельный `Platform.THREADS` publisher path.
- При выключенном flag destination остается `disabled`.

## Before Production Enablement

- Подтвердить OAuth/app setup для Threads API.
- Подтвердить допустимые scopes и publishing flow.
- Проверить rate limits, media constraints и policy boundaries на реальном app setup.
- Прогнать отдельный end-to-end smoke test в staging.

