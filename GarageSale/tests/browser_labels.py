"""On-screen labels for Selenium tests shared across apps."""
from selenium import webdriver
from selenium.webdriver.support.events import AbstractEventListener, EventFiringWebDriver


class BrowserTestIndicator(AbstractEventListener):
    """Keep the current test name visible after browser navigation and clicks."""
    test_name = ''

    def show(self, driver):
        if not self.test_name:
            return
        driver.execute_script('''
            let badge = document.getElementById('browser-test-indicator');
            if (!badge) {
                badge = document.createElement('div');
                badge.id = 'browser-test-indicator';
                badge.style.cssText = 'position:fixed;top:0;right:0;z-index:2147483647;' +
                    'max-width:95vw;padding:4px 8px;background:#172b4d;color:white;' +
                    'font:12px monospace;pointer-events:none;overflow-wrap:anywhere;';
            }
            badge.textContent = 'Running: ' + arguments[0];
            const position = () => {
                const parent = document.querySelector('dialog[open]') || document.body;
                badge.style.position = parent.tagName === 'DIALOG' ? 'sticky' : 'fixed';
                if (badge.parentNode !== parent) parent.prepend(badge);
            };
            position();
            window.browserTestIndicatorObserver?.disconnect();
            window.browserTestIndicatorObserver = new MutationObserver(position);
            window.browserTestIndicatorObserver.observe(document.body, {
                subtree: true, childList: true, attributes: true, attributeFilter: ['open'],
            });
            window.browserTestOriginalTitle ??= document.title;
            document.title = '[Test] ' + arguments[0] + ' | ' + window.browserTestOriginalTitle;
        ''', self.test_name)

    def after_navigate_to(self, url, driver):
        self.show(driver)

    def after_navigate_refresh(self, driver):
        self.show(driver)

    def after_click(self, element, driver):
        self.show(driver)

    def before_find(self, by, value, driver):
        # A form submission can finish loading after the click callback has run.
        self.show(driver)


class BrowserTestLabelMixin:
    @classmethod
    def get_driver(cls):
        indicator = BrowserTestIndicator()
        driver = EventFiringWebDriver(webdriver.Chrome(), indicator)
        driver.test_indicator = indicator
        return driver

    def setUp(self):
        name = f'{type(self).__name__}.{self._testMethodName}'
        self.selenium.test_indicator.test_name = name
        print(f'Running browser test: {name}', flush=True)
        super().setUp()
