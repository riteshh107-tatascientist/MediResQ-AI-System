"""Minimal fake of the Streamlit + Plotly APIs used by the views so page code can be smoke-tested headlessly
(catches Python/data errors; it cannot judge layout or CSS). Real launch must be verified locally."""
import sys
from contextlib import contextmanager
from types import ModuleType
from unittest.mock import MagicMock


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return getattr(_ST[0], n)   # column/tab/expander contexts expose the same widgets


_ST = [None]


class SS(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


class FakeSt(ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = SS()
        self.calls = []

    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Ctx() for _ in range(n)]

    def tabs(self, labels):
        return [_Ctx() for _ in labels]

    def _first(self, label, options, index=0, **k):
        options = list(options)
        return options[index] if options else None

    selectbox = radio = _first

    def multiselect(self, label, options, default=None, **k):
        return list(default or [])

    def button(self, *a, **k): return False
    def checkbox(self, *a, **k): return False
    def form_submit_button(self, *a, **k): return False
    def text_input(self, label, value="", **k): return value
    def text_area(self, label, value="", **k): return value
    def number_input(self, label, min_value=None, max_value=None, value=None, **k): return value if value is not None else (min_value or 0)
    def slider(self, label, a=None, b=None, value=None, step=None, **k): return value if value is not None else a
    def date_input(self, label, value=None, **k): return value
    def file_uploader(self, *a, **k): return None
    def expander(self, *a, **k): return _Ctx()
    def container(self, *a, **k): return _Ctx()
    def form(self, *a, **k): return _Ctx()
    def spinner(self, *a, **k): return _Ctx()
    sidebar = _Ctx()
    def rerun(self): pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        def f(*a, **k):
            self.calls.append(name)
        return f


def install():
    st = FakeSt()
    _ST[0] = st
    sys.modules["streamlit"] = st
    for m in ("plotly", "plotly.express", "plotly.graph_objects"):
        sys.modules[m] = MagicMock()
    return st
