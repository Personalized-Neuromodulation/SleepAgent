from pathlib import Path

from download import Downloader
from download import Result


class DummyResponse:
    status_code = 200
    url = "https://www.nature.com/articles/s41586-020-0000-0"
    headers = {"Content-Type": "text/html; charset=utf-8"}
    text = """
    <html>
      <body>
        <a href="/articles/s41586-020-0000-0_reference.pdf">Download PDF</a>
        <a href="/articles/s41586-020-0000-0_supplement.pdf">Supplementary Information</a>
      </body>
    </html>
    """


class RecordingDownloader(Downloader):
    def __init__(self, tmp_path):
        super().__init__(
            out_dir=tmp_path,
            email="test@example.com",
            delay=(0, 0),
            sources=[],
            flat_output=True,
        )
        self.tried_urls = []

    def _request_with_429_retry(self, *args, **kwargs):
        return DummyResponse()

    def try_urls(self, source, identifier, stem, urls, expected_fmt=None):
        self.tried_urls = list(urls)
        return None


def test_nature_publisher_pdf_parses_landing_page_without_synthetic_pdf_url(tmp_path):
    downloader = RecordingDownloader(tmp_path)

    downloader.publisher_pdf("10.1038/s41586-020-0000-0", "paper")

    urls = [url for url, _ in downloader.tried_urls]
    assert "https://www.nature.com/articles/s41586-020-0000-0.pdf" not in urls
    assert urls == [
        "https://www.nature.com/articles/s41586-020-0000-0_reference.pdf"
    ]


def test_nature_access_options_page_is_not_fulltext():
    body = " ".join(
        [
            "Disconnecting part of the brain sends it into a deep sleep",
            "Slow, sleep-like brainwaves persist in part of the brain.",
            "Abstract Introduction Methods Results Discussion References",
        ]
        * 120
    )
    html = f"""
    <html>
      <head><title>Disconnecting part of the brain sends it into a deep sleep | Nature</title></head>
      <body>
        <article>{body}</article>
        <section>
          <h2>Access options</h2>
          <p>Access Nature and 54 other Nature Portfolio journals</p>
          <p>Get Nature+, our best-value online-access subscription</p>
          <p>Subscribe to this journal</p>
          <p>Rent or buy this article</p>
          <p>from $1.95 to $39.95</p>
        </section>
        <section>
          <h2>Related Articles</h2>
          <p>How to detect consciousness in people, animals and maybe even AI</p>
        </section>
      </body>
    </html>
    """

    assert Downloader.classify_html_page(html) == "landing"


def test_full_article_with_access_options_sidebar_is_still_fulltext():
    sections = []
    for name in ("Abstract", "Introduction", "Methods", "Results", "Discussion", "References"):
        sections.append(
            f"<section><h2>{name}</h2>"
            + "".join(
                f"<p>{name} paragraph {i}. This paragraph contains detailed article body text "
                "about sleep physiology, experiments, analysis, and interpretation.</p>"
                for i in range(12)
            )
            + "</section>"
        )
    html = f"""
    <html>
      <body>
        <article>{''.join(sections)}</article>
        <aside>
          <h2>Access options</h2>
          <p>Subscribe to this journal</p>
          <p>Rent or buy this article</p>
        </aside>
      </body>
    </html>
    """

    assert Downloader.classify_html_page(html) == "fulltext"


def test_daily_briefing_html_is_not_article_fulltext_even_when_long():
    sections = []
    for heading in (
        "How the brain wakes up",
        "New methods revive hearts for transplants",
        "Google tech sends early quake warnings",
        "Features and opinion",
        "Five best science books this week",
    ):
        paragraphs = "".join(
            f"<p>{heading} item {i}. This newsletter paragraph summarizes a different story "
            "and links readers to another publication rather than presenting one research paper.</p>"
            for i in range(8)
        )
        sections.append(f"<section><h2>{heading}</h2>{paragraphs}</section>")
    html = f"""
    <html>
      <head><title>Daily briefing: How the brain boots up from sleep to wakefulness | Nature</title></head>
      <body><article>
        <p>Hello Nature readers, would you like to get this Briefing in your inbox free every day?</p>
        {''.join(sections)}
        <h2>QUOTE OF THE DAY</h2>
        <p>Thanks for reading, Flora Graham, senior editor, Nature Briefing.</p>
      </article></body>
    </html>
    """

    assert Downloader.classify_html_page(html) == "landing"


def test_nature_access_options_markdown_is_not_valid_fulltext(tmp_path):
    path = tmp_path / "nature-news.md"
    path.write_text(
        "\n".join([
            "Disconnecting part of the brain sends it into a deep sleep | Nature",
            "Slow, sleep-like brainwaves persist in part of the brain.",
            "Access options",
            "Access Nature and 54 other Nature Portfolio journals",
            "Subscribe to this journal",
            "Rent or buy this article",
            "from $1.95 to $39.95",
            "Related Articles",
        ] * 80),
        encoding="utf-8",
    )

    result = Result("downloaded", fmt="md", file=str(path), source="OpenAlex:md_fallback")

    assert Downloader.validate_fulltext_file(result) is False


def test_full_article_markdown_with_access_options_sidebar_is_valid(tmp_path):
    path = tmp_path / "full-article.md"
    sections = []
    for name in ("Abstract", "Introduction", "Methods", "Results", "Discussion", "References"):
        sections.append(f"## {name}")
        sections.extend(
            f"{name} paragraph {i}. This paragraph contains detailed article body text "
            "about sleep physiology, experiments, analysis, and interpretation."
            for i in range(30)
        )
    sections.extend([
        "Access options",
        "Subscribe to this journal",
        "Rent or buy this article",
    ])
    path.write_text("\n".join(sections), encoding="utf-8")

    result = Result("downloaded", fmt="md", file=str(path), source="OpenAlex:md_fallback")

    assert Downloader.validate_fulltext_file(result) is True


def test_daily_briefing_markdown_is_not_valid_article_fulltext(tmp_path):
    path = tmp_path / "daily-briefing.md"
    sections = []
    for heading in (
        "How the brain wakes up",
        "New methods revive hearts for transplants",
        "Google tech sends early quake warnings",
        "Features and opinion",
        "Five best science books this week",
    ):
        sections.append(f"## {heading}")
        sections.extend(
            f"{heading} item {i}. This newsletter paragraph summarizes a different story "
            "and links readers to another publication rather than presenting one research paper."
            for i in range(8)
        )
    path.write_text(
        "# Daily briefing: How the brain boots up from sleep to wakefulness | Nature\n\n"
        "Hello Nature readers, would you like to get this Briefing in your inbox free every day?\n\n"
        + "\n\n".join(sections)
        + "\n\n### QUOTE OF THE DAY\n\nThanks for reading, Flora Graham, senior editor, Nature Briefing.\n",
        encoding="utf-8",
    )

    result = Result("downloaded", fmt="md", file=str(path), source="OpenAlex:md_fallback")

    assert Downloader.validate_fulltext_file(result) is False


def test_txt_is_not_a_supported_fulltext_format(tmp_path):
    path = tmp_path / "full-article.txt"
    path.write_text("Abstract\n" + ("complete article paragraph " * 200), encoding="utf-8")

    result = Result("downloaded", fmt="txt", file=str(path), source="legacy")

    assert Downloader.validate_fulltext_file(result) is False


def test_downloader_does_not_create_txt_directories_or_accept_txt_assets(tmp_path):
    downloader = Downloader(
        out_dir=tmp_path,
        email="test@example.com",
        delay=(0, 0),
        sources=[],
        flat_output=False,
    )

    assert "txt" not in downloader.dirs
    assert "converted_text" not in downloader.dirs
    assert Downloader._is_fulltext_asset_url("https://example.org/article.txt", "txt") is False
