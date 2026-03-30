from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from repost_bot.errors import PermanentPublishError, TransientPublishError


@dataclass(slots=True)
class TelegramMediaClient:
    bot_token: str

    def download_file(self, file_id: str) -> dict[str, Any]:
        file_info = self._get_file(file_id)
        file_path = file_info.get("file_path")
        if not file_path:
            raise PermanentPublishError("Telegram getFile response missing file_path")

        request = urllib.request.Request(
            url=f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}",
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
        except OSError as exc:
            raise TransientPublishError(str(exc)) from exc

        filename = file_path.rsplit("/", 1)[-1] or f"{file_id}.bin"
        content_type = self._content_type_from_filename(filename)
        return {
            "filename": filename,
            "content_type": content_type,
            "content": content,
        }

    def _get_file(self, file_id: str) -> dict[str, Any]:
        encoded_payload = urllib.parse.urlencode({"file_id": file_id}).encode("utf-8")
        request = urllib.request.Request(
            url=f"https://api.telegram.org/bot{self.bot_token}/getFile",
            data=encoded_payload,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except OSError as exc:
            raise TransientPublishError(str(exc)) from exc

        if not body.get("ok"):
            raise PermanentPublishError(f"Telegram getFile failed for {file_id}")
        return body.get("result", {})

    def _content_type_from_filename(self, filename: str) -> str:
        lower_name = filename.lower()
        if lower_name.endswith(".jpg") or lower_name.endswith(".jpeg"):
            return "image/jpeg"
        if lower_name.endswith(".png"):
            return "image/png"
        if lower_name.endswith(".webp"):
            return "image/webp"
        return "application/octet-stream"
