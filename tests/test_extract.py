"""Tests for selectolax/lxml extraction."""

from __future__ import annotations

from async_web_collector.config import FieldSpec
from async_web_collector.extract import HtmlDocument, _looks_like_xpath
from fixtures import SAMPLE_HTML


def test_css_first() -> None:
    document = HtmlDocument(SAMPLE_HTML)
    value = document.extract_field(FieldSpec(name="title", selector="h2.title"))
    assert value == "First Post"


def test_css_all() -> None:
    document = HtmlDocument(SAMPLE_HTML)
    values = document.extract_field(
        FieldSpec(name="tags", selector="ul.tags li", all=True, strip=True)
    )
    assert values == ["a", "b", "c"]


def test_css_attr() -> None:
    document = HtmlDocument(SAMPLE_HTML)
    value = document.extract_field(FieldSpec(name="link", selector="a.link", attr="href"))
    assert value == "/p/1"


def test_xpath_text() -> None:
    document = HtmlDocument(SAMPLE_HTML)
    value = document.extract_field(FieldSpec(name="title", selector="//h2[@class='title']/text()"))
    assert value == "First Post"


def test_xpath_attr() -> None:
    document = HtmlDocument(SAMPLE_HTML)
    value = document.extract_field(FieldSpec(name="link", selector="//a[@class='link']/@href"))
    assert value == "/p/1"


def test_scope_records() -> None:
    document = HtmlDocument(SAMPLE_HTML)
    records = document.extract_records(
        [
            FieldSpec(name="title", selector="h2.title"),
            FieldSpec(name="price", selector="span.price"),
        ],
        scope="article.post",
    )
    assert len(records) == 2
    assert records[0]["title"] == "First Post"
    assert records[0]["price"] == "12.50"
    assert records[1]["title"] == "Second Post"


def test_xpath_scope_records() -> None:
    document = HtmlDocument(SAMPLE_HTML)
    records = document.extract_records(
        [FieldSpec(name="price", selector=".//span[@class='price']/text()")],
        scope="//article[@class='post']",
    )
    assert records == [{"price": "12.50"}, {"price": "9.00"}]


def test_missing_returns_none() -> None:
    document = HtmlDocument("<html><body><p>hi</p></body></html>")
    value = document.extract_field(FieldSpec(name="nope", selector="h1"))
    assert value is None


def test_no_records_without_match() -> None:
    document = HtmlDocument("<html><body><p>hi</p></body></html>")
    records = document.extract_records([FieldSpec(name="t", selector="h1")], scope="div")
    assert records == []


def test_looks_like_xpath() -> None:
    assert _looks_like_xpath("//div")
    assert _looks_like_xpath("/html/body")
    assert _looks_like_xpath(".//span")
    assert _looks_like_xpath("(//a)[1]")
    assert not _looks_like_xpath("div")
    assert not _looks_like_xpath(".title")
