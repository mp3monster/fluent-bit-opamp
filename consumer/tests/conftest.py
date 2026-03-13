import pathlib
import sys


def pytest_configure() -> None:
    root = pathlib.Path(__file__).resolve().parents[2]
    src = root / "consumer" / "src"
    for path in (root, src):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
