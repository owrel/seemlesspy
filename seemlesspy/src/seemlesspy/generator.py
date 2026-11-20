import json
import types
import typing
from collections.abc import Sequence

from .descriptor import Class

_TS_SCALARS = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
    type(None): "null",
}

_TS_IMPORT = 'import { connector } from "seemlessts";'


def generate_ts(cls: Class) -> str:
    return f"{_TS_IMPORT}\n\n{generate_class(cls)}"


def generate_module(classes: Sequence[Class]) -> str:
    bodies = [generate_class(cls) for cls in classes]

    if not bodies:
        return f"{_TS_IMPORT}\n"

    body = "\n\n".join(bodies)
    return f"{_TS_IMPORT}\n\n{body}\n"


def generate_class(cls: Class) -> str:
    class_name = cls.cls.__qualname__
    lines: list[str] = [
        f"export class {cls.name} {{",
        f"  private cls_name: string = {json.dumps(class_name)};",
        "  private instance_id: string | null = null;",
        "  private ready: Promise<void>;",
        "  private watchers = new Map<string, Set<(value: unknown) => void>>();",
        "  private stopWatchers: (() => void) | null = null;",
        "",
    ]

    constructor_params: list[str] = []
    constructor_args: list[str] = []
    for name, param_type in cls.constructor.params:
        constructor_params.append(f"{name}: {_ts_type(param_type)}")
        constructor_args.append(f"[{json.dumps(name)}, {name}]")
    lines.extend(
        (
            f"  constructor({', '.join(constructor_params)}) {{",
            "    this.ready = connector",
            "      .send({",
        )
    )
    lines.extend(
        _contract_lines(
            "constructor", "__init__", constructor_args, "        ", "null"
        )
    )
    lines.extend(
        (
            "      })",
            "      .then((result) => {",
            "        this.instance_id = result as string;",
            "      });",
            "  }",
            "",
        )
    )

    properties: list[tuple[str, str]] = []

    for name, member in cls.members.items():
        if member.kind == "property":
            ret = _ts_type(member.ret)
            properties.append((name, ret))
            lines.extend(
                (
                    f"  get {name}(): Promise<{ret}> {{",
                    "    return this.ready.then(async () => {",
                    "      const result = await connector.send({",
                )
            )
            lines.extend(
                _contract_lines(
                    "property", name, [], "        ", "this.instance_id"
                )
            )
            lines.extend(
                (
                    "      });",
                    f"      return result as {ret};",
                    "    });",
                    "  }",
                    "",
                )
            )
            continue

        method_params: list[str] = []
        method_args: list[str] = []
        for param_name, param_type in member.params:
            method_params.append(f"{param_name}: {_ts_type(param_type)}")
            method_args.append(f"[{json.dumps(param_name)}, {param_name}]")
        ret = _ts_return_type(member.ret)
        signature = (
            f"  async {name}({', '.join(method_params)}): Promise<{ret}> {{"
        )
        lines.extend((signature, "    await this.ready;"))
        if member.ret is None:
            lines.append("    await connector.send({")
            lines.extend(
                _contract_lines(
                    "method", name, method_args, "      ", "this.instance_id"
                )
            )
            lines.append("    });")
        else:
            lines.append("    const result = await connector.send({")
            lines.extend(
                _contract_lines(
                    "method", name, method_args, "      ", "this.instance_id"
                )
            )
            lines.extend(("    });", f"    return result as {ret};"))
        lines.extend(("  }", ""))

    lines.extend(
        (
            "  private async watch(",
            "    member: string,",
            "    callback: (value: unknown) => void,",
            "  ): Promise<() => void> {",
            "    await this.ready;",
            "",
            "    if (this.stopWatchers === null) {",
            "      this.stopWatchers = connector.onUpdate((update) => {",
            "        if (update.instance_id !== this.instance_id) {",
            "          return;",
            "        }",
            "",
            "        const listeners = this.watchers.get(update.member);",
            "",
            "        if (listeners === undefined) {",
            "          return;",
            "        }",
            "",
            "        for (const listener of listeners) {",
            "          listener(update.value);",
            "        }",
            "      });",
            "    }",
            "",
            "    let listeners = this.watchers.get(member);",
            "",
            "    if (listeners === undefined) {",
            "      listeners = new Set();",
            "      this.watchers.set(member, listeners);",
            "    }",
            "",
            "    listeners.add(callback);",
            "",
            "    const value = await connector.send({",
            '      kind: "subscribe",',
            "      cls_name: this.cls_name,",
            "      instance_id: this.instance_id,",
            "      member,",
            "      params: [],",
            "    });",
            "",
            "    callback(value);",
            "",
            "    return () => {",
            "      listeners.delete(callback);",
            "      void connector.send({",
            '        kind: "unsubscribe",',
            "        cls_name: this.cls_name,",
            "        instance_id: this.instance_id,",
            "        member,",
            "        params: [],",
            "      });",
            "    };",
            "  }",
            "",
        )
    )

    for name, ret in properties:
        method_name = f"watch{_pascal_case(name)}"
        signature = (
            f"    return this.watch({json.dumps(name)}, (value) => "
            f"callback(value as {ret}));"
        )
        lines.extend(
            (
                f"  async {method_name}(",
                f"    callback: (value: {ret}) => void,",
                "  ): Promise<() => void> {",
                signature,
                "  }",
                "",
            )
        )

    lines.extend(
        (
            "  async release(): Promise<void> {",
            "    await this.ready;",
            "",
            "    if (this.stopWatchers !== null) {",
            "      this.stopWatchers();",
            "      this.stopWatchers = null;",
            "    }",
            "",
            "    await connector.send({",
            '      kind: "release",',
            "      cls_name: this.cls_name,",
            "      instance_id: this.instance_id,",
            '      member: "",',
            "      params: [],",
            "    });",
            "    this.instance_id = null;",
            "  }",
            "",
        )
    )

    while not lines[-1]:
        lines.pop()
    lines.append("}")
    return "\n".join(lines)


def _pascal_case(name: str) -> str:
    parts = name.split("_")
    result = ""

    for part in parts:
        result += part[:1].upper() + part[1:]

    return result


def _contract_lines(
    kind: str,
    member: str,
    args: list[str],
    indent: str,
    instance_id: str,
) -> list[str]:
    return [
        f"{indent}kind: {json.dumps(kind)},",
        f"{indent}cls_name: this.cls_name,",
        f"{indent}instance_id: {instance_id},",
        f"{indent}member: {json.dumps(member)},",
        f"{indent}params: [{', '.join(args)}],",
    ]


def _ts_type(annotation: object) -> str:
    if annotation is None or annotation is type(None):
        return "null"

    if annotation is typing.Any:
        return "any"

    if annotation is list or annotation is tuple or annotation is set:
        return "unknown[]"

    if annotation is dict:
        return "Record<string, unknown>"

    origin = typing.get_origin(annotation)

    if origin is types.UnionType or origin is typing.Union:
        arguments = typing.get_args(annotation)
        mapped = list(dict.fromkeys([_ts_type(arg) for arg in arguments]))
        return " | ".join(mapped)

    if origin is typing.Literal:
        return " | ".join(
            [json.dumps(value) for value in typing.get_args(annotation)]
        )

    if origin is list or origin is Sequence:
        arguments = typing.get_args(annotation)

        if arguments:
            return f"{_ts_type(arguments[0])}[]"

        return "unknown[]"

    if origin is tuple:
        arguments = typing.get_args(annotation)

        if not arguments:
            return "unknown[]"

        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return f"{_ts_type(arguments[0])}[]"

        parts = [_ts_type(arg) for arg in arguments]
        return "[" + ", ".join(parts) + "]"

    if origin is set:
        arguments = typing.get_args(annotation)

        if arguments:
            return f"{_ts_type(arguments[0])}[]"

        return "unknown[]"

    if origin is dict:
        arguments = typing.get_args(annotation)

        if len(arguments) == 2:
            return f"Record<{_ts_type(arguments[0])}, {_ts_type(arguments[1])}>"

        return "Record<string, unknown>"

    if isinstance(annotation, type):
        return _TS_SCALARS.get(annotation, annotation.__name__)

    raise NotImplementedError(f"TODO: TS type for {annotation!r}")


def _ts_return_type(annotation: object) -> str:
    if annotation is None:
        return "void"
    return _ts_type(annotation)
