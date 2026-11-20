from types import FunctionType


class MissingAnnotationError(Exception):
    def __init__(self, cls: type, func: FunctionType, label: str) -> None:
        code = func.__code__
        self.cls = cls
        self.func = func
        self.label = label
        self.file = code.co_filename
        self.line = code.co_firstlineno
        super().__init__(
            f"{cls.__name__}.{func.__name__} "
            f'(File "{self.file}", line {self.line + 1}): missing type annotation on {label}'
        )
