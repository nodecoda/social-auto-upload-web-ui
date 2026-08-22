"""primitives 原语单测共享工具：FakePage/FakeElement 记录交互调用。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class FakeElement:
    """链式 locator 假元素：记录调用，按 selector 可配置 count。"""

    def __init__(self, page, selector="", count=1, attributes=None):
        self._page = page
        self._selector = selector
        self._count = count
        self._attributes = attributes or {}

    async def count(self):
        return self._count

    async def click(self, *args, **kwargs):
        self._page.calls.append(("click", self._selector, kwargs))

    async def fill(self, value, *args, **kwargs):
        self._page.calls.append(("fill", self._selector, value))

    async def type(self, text, *args, **kwargs):
        self._page.calls.append(("type", self._selector, text))

    async def set_input_files(self, path, *args, **kwargs):
        self._page.calls.append(("set_input_files", self._selector, path))

    async def hover(self, *args, **kwargs):
        self._page.calls.append(("hover", self._selector, kwargs))

    async def wait_for(self, *args, **kwargs):
        self._page.calls.append(("wait_for", self._selector, kwargs))

    async def get_attribute(self, name):
        return self._attributes.get(name)

    async def is_checked(self):
        return self._attributes.get("checked", False)

    async def text_content(self):
        return self._attributes.get("text", "1")

    async def inner_text(self):
        return self._attributes.get("text", "1")

    async def evaluate(self, fn):
        self._page.calls.append(("evaluate", self._selector, fn))
        return True

    def locator(self, selector):
        return FakeElement(self._page, selector=f"{self._selector} >> {selector}",
                           count=self._count, attributes=self._attributes)

    def filter(self, **kwargs):
        return self

    def nth(self, index):
        nth_texts = self._attributes.get("nth_texts")
        if nth_texts and index < len(nth_texts):
            attrs = dict(self._attributes, text=nth_texts[index])
            return FakeElement(self._page, selector=self._selector,
                               count=self._count, attributes=attrs)
        return self

    @property
    def first(self):
        return self


class FakePage:
    """最小 Playwright Page 假对象：locator 链 + 键盘 + 文件选择器。"""

    def __init__(self, counters=None, attributes=None):
        self.calls = []
        self.counters = counters or {}
        self.attributes = attributes or {}
        self.keyboard = FakeKeyboard(self)
        self._fc_files = []

    def locator(self, selector):
        attrs = self.attributes.get(selector, {})
        count = self.counters.get(selector, 1)
        if "nth_texts" in attrs:
            count = len(attrs["nth_texts"])
        return FakeElement(self, selector=selector, count=count, attributes=attrs)

    async def wait_for_selector(self, selector, **kwargs):
        return FakeElement(self, selector=selector,
                           count=self.counters.get(selector, 1),
                           attributes=self.attributes.get(selector, {}))

    async def click(self, selector, **kwargs):
        self.calls.append(("page.click", selector, kwargs))

    async def evaluate(self, fn, *args):
        self.calls.append(("page.evaluate", fn, args))
        return True

    async def input_value(self, selector):
        return "2026-06-22 13:00"

    def get_by_role(self, role, name="", exact=False):
        return FakeElement(self, selector=f"role={role} name={name}")

    def expect_file_chooser(self, timeout=None):
        return _FakeFileChooserCtx(self)

    async def screenshot(self, **kwargs):
        pass

    async def wait_for_timeout(self, ms):
        pass


class FakeKeyboard:
    def __init__(self, page):
        self._page = page

    async def press(self, key):
        self._page.calls.append(("keyboard.press", key, None))

    async def type(self, text, **kwargs):
        self._page.calls.append(("keyboard.type", text, kwargs))


class _FakeFileChooser:
    def __init__(self, page):
        self._page = page

    async def set_files(self, path):
        self._page.calls.append(("file_chooser.set_files", path, None))


class _FakeFileChooserCtx:
    def __init__(self, page):
        self._page = page
        self._value = _FakeFileChooser(page)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def value(self):
        return self._get_value()

    async def _get_value(self):
        return self._value
