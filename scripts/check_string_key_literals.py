# Copyright 2026 mp3monster.org
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#!/usr/bin/env python3
"""Enforce extracting repeated key-like string literals into module constants."""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
MIN_LITERAL_LENGTH = 8
MIN_DUPLICATE_COUNT = 2
IGNORED_SUFFIXES = ("_pb2.py", "_pb2.pyi")


def _is_docstring_node(node: ast.Constant, parent: ast.AST) -> bool:
    if not isinstance(node.value, str):
        return False
    if not isinstance(parent, ast.Expr):
        return False
    container = getattr(parent, "_parent", None)
    if not isinstance(container, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    if not container.body:
        return False
    return container.body[0] is parent


def _is_module_constant_assignment(node: ast.Assign) -> bool:
    if not isinstance(getattr(node, "_parent", None), ast.Module):
        return False
    if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
        return False
    for target in node.targets:
        if isinstance(target, ast.Name) and target.id.isupper():
            return True
    return False


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            setattr(child, "_parent", node)

    existing_constant_values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_module_constant_assignment(node):
            existing_constant_values.add(node.value.value)

    occurrences: dict[str, list[int]] = defaultdict(list)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        parent = getattr(node, "_parent", None)
        if parent is None or _is_docstring_node(node, parent):
            continue

        value = node.value
        if len(value) < MIN_LITERAL_LENGTH:
            continue
        if not KEY_PATTERN.fullmatch(value):
            continue

        occurrences[value].append(node.lineno)

    errors: list[str] = []
    for value, lines in sorted(occurrences.items()):
        if len(lines) < MIN_DUPLICATE_COUNT:
            continue
        if value in existing_constant_values:
            continue
        joined = ", ".join(str(line) for line in lines[:4])
        suffix = "..." if len(lines) > 4 else ""
        errors.append(
            f"{path}:{lines[0]} repeated key-like string literal "
            f"'{value}' (lines: {joined}{suffix})"
        )
    return errors


def main(argv: list[str]) -> int:
    files = [
        Path(arg) for arg in argv[1:] if arg.endswith(".py") and not arg.endswith(IGNORED_SUFFIXES)
    ]
    if not files:
        return 0

    errors: list[str] = []
    for path in files:
        if not path.exists():
            continue
        errors.extend(check_file(path))

    if not errors:
        return 0

    print("Repeated key-like literals found. Extract these to constants:")
    for error in errors:
        print(f"  - {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
