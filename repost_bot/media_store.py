from __future__ import annotations

import os
import uuid
from dataclasses import dataclass


@dataclass(slots=True)
class LocalMediaStore:
    storage_path: str
    public_base_url: str

    def store_file(self, media_file: dict) -> str:
        os.makedirs(self.storage_path, exist_ok=True)
        extension = self._extension_from_filename(media_file["filename"])
        filename = f"{uuid.uuid4().hex}{extension}"
        destination_path = os.path.join(self.storage_path, filename)
        with open(destination_path, "wb") as handle:
            handle.write(media_file["content"])
        return f"{self.public_base_url.rstrip('/')}/{filename}"

    def _extension_from_filename(self, filename: str) -> str:
        _, extension = os.path.splitext(filename)
        return extension or ".bin"
