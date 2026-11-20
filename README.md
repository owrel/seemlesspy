# seemlesspy

Call Python objects from TypeScript over a WebSocket. Python classes are exposed as generated TypeScript classes; each operation is a contract (`constructor`, `method`, `property`, `release`, `subscribe`, `unsubscribe`).

- `seemlesspy/` — Python package: FastAPI endpoint, registry, TS generator, CLI.
- `seemlessts/` — TypeScript connector.

## Install

Python (>= 3.14):

```sh
uv add "seemlesspy @ git+https://github.com/Owrel/seemlesspy.git#subdirectory=seemlesspy"
uv add "uvicorn[standard]"   # WebSocket support
```

TypeScript (not published to npm):

```sh
git clone https://github.com/Owrel/seemlesspy.git
cd seemlesspy/seemlessts && npm install && npm run build
# then, in your project:
npm install /path/to/seemlesspy/seemlessts
```

## Usage

`server.py`:

```python
from fastapi import FastAPI

from seemlesspy.base import SeemlessPy
from seemlesspy.connector import setup_websocket
from seemlesspy.decorators import seemlessmethod, seemlessproperty


class Counter(SeemlessPy):
    def __init__(self, value: int):
        self._value = value

    @seemlessproperty
    @property
    def value(self) -> int:
        return self._value

    @seemlessmethod
    def increment(self, by: int) -> int:
        self._value += by
        return self._value


app = FastAPI()
setup_websocket(app)   # endpoint: /ws
```

Run `uv run uvicorn server:app --port 8000`, then generate the client:

```sh
seemlesspy server.py -o client/generated.ts
```

```ts
import { Counter } from "./generated";

const counter = new Counter(0);
console.log(await counter.value); // 0
console.log(await counter.increment(5)); // 5

await counter.release();
```

The connector opens the socket on first use. Default URL: `ws://127.0.0.1:8000/ws`; change it with `configureConnector({ url })` from `seemlessts`. Without a bundler, map `seemlessts` to `dist/connector.js` in an import map.

Supported annotations: `str`, `int`, `float`, `bool`, `None`, bare classes, `Any`, `Self`, `Literal[...]`, `list[X]`, `Sequence[X]`, `set[X]`, `dict[K, V]`, `tuple[X]` / `tuple[X, ...]` and unions such as `X | None` (nested combinations included). Values are validated and converted with Pydantic's `TypeAdapter` (strict JSON mode).

Custom values can be converted both ways with `register_transformer(Foo, to_dict, from_dict)`; either converter is optional and falls back to `obj.to_json()` / `Foo.from_json(data)`. Lists, tuples and dict values are walked in both directions.

## CLI

```sh
seemlesspy [path] -o <file|dir> [--split] [-e dir] [-c pyproject.toml] [--save-config]
```

- `path`: Python file or recursive directory (default `.`)
- `--split`: one `<Class>.ts` per class, into a directory
- `-e/--env`: prepend to `sys.path` before importing
- `-c/--config`: read `[tool.seemlesspy]`; CLI options win
- `--save-config`: write the effective options to `[tool.seemlesspy]`

## Live updates

Generated properties get `watch<Property>(callback)`, which returns an unsubscribe function:

```ts
const value = ref(0);
const stop = await counter.watchValue((next) => {
    value.value = next;
});
```

- A method contract pushes subscribed properties after it returns.
- Restrict the pushed properties with `@seemlessmethod(changes=["value"])`.
- Helpers that are not RPC methods: `@seemlesschange(seemless_cls=Counter, changes=["value"])`.
- Changes from background code: `await manager.notify(instance)`.

## Wrapping existing classes

```python
SeemlessFoo = seemlessify(Foo, methods=["m"], properties=["p"])
```

## Security

Sessions are per connection, instance ids are unguessable, contracts are validated against the class descriptor, and broadcasts are room-scoped. Not handled: authentication, authorization, TLS, rate limits. Do not expose the endpoint publicly without those.

## Layout

```
seemlesspy/     Python package
seemlessts/     TypeScript package
```
