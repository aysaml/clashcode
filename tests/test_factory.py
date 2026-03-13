"""factory.py 单元测试"""

import pytest
from clashcode.core.factory import (
    AdapterFactory,
    PythonAdapter,
    GenericAdapter,
    LANGUAGE_MAP,
)
from clashcode.core.models import ChangeType, FileChange


class TestAdapterFactory:
    def test_detect_python(self):
        assert AdapterFactory.detect_language("test.py") == "python"
        assert AdapterFactory.detect_language("dir/module.py") == "python"

    def test_detect_javascript(self):
        assert AdapterFactory.detect_language("app.js") == "javascript"
        assert AdapterFactory.detect_language("component.jsx") == "javascript"

    def test_detect_typescript(self):
        assert AdapterFactory.detect_language("index.ts") == "typescript"
        assert AdapterFactory.detect_language("App.tsx") == "typescript"

    def test_detect_unknown(self):
        assert AdapterFactory.detect_language("readme.md") is None
        assert AdapterFactory.detect_language("data.csv") is None

    def test_get_python_adapter(self):
        adapter = AdapterFactory.get_adapter("python")
        assert isinstance(adapter, PythonAdapter)

    def test_get_generic_adapter(self):
        adapter = AdapterFactory.get_adapter("unknown_lang")
        assert isinstance(adapter, GenericAdapter)


class TestPythonAdapter:
    def test_extract_functions(self):
        adapter = PythonAdapter()
        fc = FileChange(
            file_path="test.py",
            change_type=ChangeType.MODIFIED,
            new_content="def foo():\n    pass\n\nasync def bar():\n    pass\n\nclass MyClass:\n    pass\n",
        )
        functions = adapter.extract_changed_functions(fc)
        assert "foo" in functions
        assert "bar" in functions
        assert "MyClass" in functions

    def test_extract_no_functions(self):
        adapter = PythonAdapter()
        fc = FileChange(
            file_path="test.py",
            change_type=ChangeType.MODIFIED,
            new_content="x = 1\ny = 2\n",
        )
        functions = adapter.extract_changed_functions(fc)
        assert len(functions) == 0

    def test_extract_from_none_content(self):
        adapter = PythonAdapter()
        fc = FileChange(
            file_path="test.py",
            change_type=ChangeType.DELETED,
            new_content=None,
        )
        functions = adapter.extract_changed_functions(fc)
        assert len(functions) == 0


class TestGenericAdapter:
    def test_extract_js_functions(self):
        adapter = GenericAdapter()
        fc = FileChange(
            file_path="app.js",
            change_type=ChangeType.MODIFIED,
            new_content="function getData() {\n}\nexport const handler = async () => {\n}\n",
        )
        functions = adapter.extract_changed_functions(fc)
        assert "getData" in functions
        assert "handler" in functions

    def test_extract_go_functions(self):
        adapter = GenericAdapter()
        fc = FileChange(
            file_path="main.go",
            change_type=ChangeType.MODIFIED,
            new_content="func main() {\n}\nfunc handleRequest() {\n}\n",
        )
        functions = adapter.extract_changed_functions(fc)
        assert "main" in functions
        assert "handleRequest" in functions
