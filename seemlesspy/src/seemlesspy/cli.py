import argparse
import importlib
import json
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .generator import generate_module, generate_ts
from .holder import _descriptor

_IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="seemlesspy",
        description="Generate TypeScript classes from seemlesspy classes.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Python file or directory to search (default: .)",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="pyproject.toml with [tool.seemlesspy] to use as defaults",
    )
    parser.add_argument(
        "-e",
        "--env",
        default=None,
        help="directory prepended to sys.path before importing",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="output file, or output directory with --split",
    )
    parser.add_argument(
        "--split",
        action="store_true",
        default=None,
        help="write one file per class into the output directory",
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="write the effective options to [tool.seemlesspy]",
    )
    args = parser.parse_args(argv)

    config: dict[str, Any] = {}
    config_path: Path | None = None

    if args.config is not None:
        config_path = Path(args.config)
        config = _load_config(config_path)
        config_path = config_path.resolve()

    cwd = Path.cwd()
    config_dir = config_path.parent if config_path is not None else cwd

    if args.path is not None:
        path_value = args.path
        path_base = cwd
    else:
        path_value = _config_string(config, "path") or "."
        path_base = config_dir

    if args.env is not None:
        env_value: str | None = args.env
        env_base = cwd
    else:
        env_value = _config_string(config, "env")
        env_base = config_dir

    if args.output is not None:
        output_value: str | None = args.output
        output_base = cwd
    else:
        output_value = _config_string(config, "output")
        output_base = config_dir

    if args.split is not None:
        split = args.split
    else:
        split = _config_bool(config, "split", default=False)

    if output_value is None:
        raise SystemExit("--output is required, or set output in --config")

    start = _resolve_path(path_value, path_base)
    output = _resolve_path(output_value, output_base)
    env = _resolve_path(env_value, env_base) if env_value is not None else None

    if env is not None:
        sys.path.insert(0, str(env))

    root = start if start.is_dir() else start.parent
    _load_files(root, _find_files(start, env))

    classes = list(_descriptor.classes.values())

    if split:
        output.mkdir(parents=True, exist_ok=True)
        for cls in classes:
            target = output / f"{cls.name}.ts"
            target.write_text(generate_ts(cls) + "\n")
            print(target)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(generate_module(classes))
        print(output)

    if args.save_config:
        pyproject = config_path

        if pyproject is None:
            pyproject = _find_pyproject(start)

        if pyproject is None:
            raise SystemExit("no pyproject.toml found")

        values = _config_values(
            path_value, env_value, output_value, split=split
        )
        _write_config(pyproject, values)
        print(pyproject)


def _load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"config file not found: {path}")

    with path.open("rb") as file:
        data = tomllib.load(file)

    config = data.get("tool", {}).get("seemlesspy")

    if not isinstance(config, dict):
        raise SystemExit(f"missing [tool.seemlesspy] in {path}")

    return config


def _config_string(config: dict[str, Any], key: str) -> str | None:
    value = config.get(key)

    if value is None:
        return None

    if not isinstance(value, str):
        raise SystemExit(f"[tool.seemlesspy] {key} must be a string")

    return value


def _config_bool(config: dict[str, Any], key: str, *, default: bool) -> bool:
    value = config.get(key, default)

    if not isinstance(value, bool):
        raise SystemExit(f"[tool.seemlesspy] {key} must be a boolean")

    return value


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value)

    if path.is_absolute():
        return path

    return base / path


def _find_files(start: Path, env: Path | None) -> list[Path]:
    if start.is_file():
        return [start]

    if not start.is_dir():
        raise SystemExit(f"not a file or directory: {start}")

    start_resolved = start.resolve()
    excluded: Path | None = None

    if env is not None:
        env_resolved = env.resolve()
        if env_resolved != start_resolved and env_resolved.is_relative_to(
            start_resolved
        ):
            excluded = env_resolved

    files: list[Path] = []

    for path in sorted(start.rglob("*.py")):
        if _is_ignored(path.relative_to(start)):
            continue
        if excluded is not None and excluded in path.resolve().parents:
            continue
        files.append(path)

    return files


def _is_ignored(relative: Path) -> bool:
    return any(part in _IGNORED_DIRS for part in relative.parts)


def _load_files(root: Path, files: Sequence[Path]) -> None:
    sys.path.insert(0, str(root))

    for file in files:
        name = _module_name(root, file)

        if not name:
            name = root.name
            sys.path.insert(0, str(root.parent))

        importlib.import_module(name)


def _module_name(root: Path, file: Path) -> str:
    parts = list(file.relative_to(root).parts)

    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = Path(parts[-1]).stem

    return ".".join(parts)


def _find_pyproject(start: Path) -> Path | None:
    current = start.resolve()

    if current.is_file():
        current = current.parent

    for directory in (current, *current.parents):
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate

    return None


def _config_values(
    path: str,
    env: str | None,
    output: str,
    *,
    split: bool,
) -> dict[str, str]:
    values: dict[str, str] = {"path": json.dumps(path)}

    if env is not None:
        values["env"] = json.dumps(env)

    values["output"] = json.dumps(output)
    values["split"] = json.dumps(split)

    return values


def _write_config(pyproject: Path, values: dict[str, str]) -> None:
    lines = pyproject.read_text().splitlines()
    start = None

    for index, line in enumerate(lines):
        if line.strip() == "[tool.seemlesspy]":
            start = index
            break

    block = ["[tool.seemlesspy]"]
    for key, value in values.items():
        block.append(f"{key} = {value}")

    if start is None:
        while lines and not lines[-1]:
            lines.pop()
        if lines:
            lines.append("")
        lines.extend(block)
    else:
        end = len(lines)
        for index in range(start + 1, len(lines)):
            if lines[index].strip().startswith("["):
                end = index
                break
        lines[start:end] = block

    pyproject.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
