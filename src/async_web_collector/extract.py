"""HTML extraction using selectolax (CSS) and lxml (XPath)."""

from __future__ import annotations

from typing import Any

from lxml import html as lxml_html
from selectolax.lexbor import LexborHTMLParser

from async_web_collector.config import FieldSpec

_XPATH_PREFIXES = ("/", "(", "./", "../")
Html = str | bytes


def _looks_like_xpath(selector: str) -> bool:
    return selector.strip().startswith(_XPATH_PREFIXES)


def _resolve(selector: str, declared: str = "auto") -> tuple[str, str]:
    """Return ``(kind, selector)`` resolving auto-detection and prefixes."""
    stripped = selector.strip()
    lowered = stripped.lower()
    if declared == "xpath" or lowered.startswith("xpath:"):
        value = stripped.split(":", 1)[1].strip() if lowered.startswith("xpath:") else selector
        return "xpath", value
    if declared == "css" or lowered.startswith("css:"):
        value = stripped.split(":", 1)[1].strip() if lowered.startswith("css:") else selector
        return "css", value
    if _looks_like_xpath(stripped):
        return "xpath", selector
    return "css", selector


class HtmlDocument:
    """Lazy dual-backend document: selectolax for CSS, lxml for XPath."""

    def __init__(self, html: Html) -> None:
        self._html = html
        self._css: LexborHTMLParser | None = None
        self._lxml: Any = None
        self._lxml_ready = False

    @property
    def css_tree(self) -> LexborHTMLParser:
        if self._css is None:
            self._css = LexborHTMLParser(self._html)
        return self._css

    def _lxml_tree(self) -> Any:
        if not self._lxml_ready:
            try:
                self._lxml = lxml_html.fromstring(self._html)
            except (ValueError, TypeError):  # pragma: no cover - malformed input
                self._lxml = None
            self._lxml_ready = True
        return self._lxml

    def _css_value(self, node: Any, field: FieldSpec) -> Any:
        if field.attr == "text":
            return node.text(deep=True, separator=field.separator, strip=field.strip)
        if field.attr == "html":
            return node.html
        return node.attributes.get(field.attr)

    def _xpath_value(self, value: Any, field: FieldSpec) -> Any:
        if isinstance(value, str):
            return value.strip() if field.strip else value
        if hasattr(value, "tag"):
            if field.attr == "text":
                text = value.text_content()
                return text.strip() if field.strip else text
            if field.attr == "html":
                return lxml_html.tostring(value, encoding="unicode")
            return value.get(field.attr)
        return value

    def extract_field(self, field: FieldSpec) -> Any:
        """Extract a single value according to ``field``."""
        kind, selector = _resolve(field.selector, field.selector_type)
        if kind == "xpath":
            tree = self._lxml_tree()
            raw = tree.xpath(selector) if tree is not None else []
            values = [self._xpath_value(item, field) for item in raw]
        else:
            values = [self._css_value(node, field) for node in self.css_tree.css(selector)]
        values = [value for value in values if value not in (None, "")]
        if field.all:
            return values
        return values[0] if values else None

    def _containers(self, scope: str | None) -> list[Html | None]:
        if not scope:
            return [None]
        kind, selector = _resolve(scope)
        if kind == "xpath":
            tree = self._lxml_tree()
            if tree is None:
                return []
            return [lxml_html.tostring(el, encoding="unicode") for el in tree.xpath(selector)]
        return [node.html for node in self.css_tree.css(selector)]

    def extract_records(
        self,
        fields: list[FieldSpec],
        scope: str | None = None,
    ) -> list[dict[str, Any]]:
        """Extract records, one per scope match (or one for the whole page)."""
        records: list[dict[str, Any]] = []
        for container in self._containers(scope):
            document = self if container is None else HtmlDocument(container)
            records.append({field.name: document.extract_field(field) for field in fields})
        return records
