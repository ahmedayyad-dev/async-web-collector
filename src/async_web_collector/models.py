"""Data models shared across the collector."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FetchResult:
    """Outcome of a single HTTP fetch."""

    url: str
    status_code: int | None = None
    content: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    attempts: int = 0
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        """Whether the fetch produced a successful (2xx) response."""
        return self.error is None and self.status_code is not None and 200 <= self.status_code < 300

    @property
    def body(self) -> str:
        """Decoded response body using the declared charset when available."""
        charset = "utf-8"
        content_type = self.headers.get("content-type") or self.headers.get("Content-Type") or ""
        for part in content_type.split(";"):
            part = part.strip()
            if part.lower().startswith("charset="):
                charset = part.split("=", 1)[1].strip().strip("\"'")
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")
