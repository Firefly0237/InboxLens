from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from inbox_lens.models import RawMail


class MailSource(ABC):
    @abstractmethod
    def fetch_since(self, since: datetime, limit: int | None = None) -> list[RawMail]:
        raise NotImplementedError
