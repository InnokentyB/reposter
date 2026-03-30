from __future__ import annotations

from repost_bot.storage import SqliteRepository


def render_status_report(repository: SqliteRepository, limit: int = 20) -> str:
    counts = repository.get_delivery_status_counts()
    stuck_jobs = repository.list_stuck_delivery_jobs(limit=limit)
    recent_errors = repository.list_recent_delivery_errors(limit=limit)

    lines: list[str] = ["Delivery Status Summary"]
    if not counts:
        lines.append("No delivery jobs found.")
        return "\n".join(lines)

    for status, count in counts.items():
        lines.append(f"{status}: {count}")

    lines.append("")
    lines.append("Stuck Or Due Jobs")
    if not stuck_jobs:
        lines.append("none")
    else:
        for row in stuck_jobs:
            lines.append(
                f"{row['id']} | status={row['status']} | attempts={row['attempt_count']} | "
                f"next_attempt_at={row['next_attempt_at']} | error={row['last_error_code'] or '-'}"
            )

    lines.append("")
    lines.append("Recent Errors")
    if not recent_errors:
        lines.append("none")
    else:
        for row in recent_errors:
            lines.append(
                f"{row['id']} | status={row['status']} | "
                f"{row['last_error_code'] or '-'} | {row['last_error_message'] or '-'}"
            )

    return "\n".join(lines)
