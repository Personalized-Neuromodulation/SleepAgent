import random
import logging

from playwright.sync_api import sync_playwright


logger = logging.getLogger(__name__)


class BrowserManager:
    """
    浏览器管理器
    当前使用 Playwright
    """

    def __init__(self, user_agents=None):

        self.user_agents = user_agents or []

        self.playwright = None
        self.browser = None
        self.page = None


    def start(self):

        if self.browser:
            return


        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled"
            ]
        )


        self.page = self.browser.new_page(
            viewport={
                "width":1920,
                "height":1080
            },
            user_agent=random.choice(
                self.user_agents
            ) if self.user_agents else None
        )


        logger.info(
            "Playwright browser started"
        )


    def get_html(self, url):

        if self.page is None:
            self.start()


        try:

            self.page.goto(
                url,
                timeout=60000,
                wait_until="domcontentloaded"
            )

            return self.page.content()


        except Exception as e:

            logger.warning(
                f"Browser loading failed: {e}"
            )

            return None



    def close(self):

        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()