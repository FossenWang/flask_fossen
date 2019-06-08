from typing import Mapping, Callable

from .exceptions import ValidationError


class LoadResult:
    def __init__(self, data, errors, invalid_data):
        self.data = data
        self.errors = errors
        self.invalid_data = invalid_data

    def __repr__(self):
        return (
            f'LoadResult(data={self.data}, '
            f'errors={self.format_errors()}, '
            f'invalid_data={self.invalid_data})'
        )

    def __str__(self):
        if self.is_valid:
            return str(self.data)
        return str(self.format_errors())

    def format_errors(self):
        return {k: str(self.errors[k]) for k in self.errors}

    @property
    def is_valid(self):
        return not self.errors


class ErrorMessageMixin:
    default_error_class = ValidationError
    default_error_messages = {}
    unknown_error = "Unknown error."

    def collect_error_messages(self, error_messages: dict = None):
        """
        Collect default error message from self and parent classes.

        :param error_messages: message dict, defaults to None
        :type error_messages: dict, optional
        """
        messages = {}
        for cls in reversed(self.__class__.__mro__):
            messages.update(getattr(cls, 'default_error_messages', {}))
        messages.update(error_messages or {})
        self.error_messages = messages

    def error(self, error_key: str, error_class=None):
        if not error_class:
            error_class = self.default_error_class
        raise error_class(
            self.error_messages.get(error_key, self.unknown_error))


def get_attr_or_item(obj, name):
    if isinstance(obj, Mapping):
        return obj[name]
    return getattr(obj, name)


def get_item(mapping, key):
    return mapping[key]


dump_from_attribute_or_key = get_attr_or_item
dump_from_attribute = getattr
dump_from_key = get_item


class _Missing:
    def __repr__(self):
        return '<catalyst.missing>'

# Default value for field args `dump_default` and `load_default`
# which means that the field does not exist in data.
# KeyError or AttributeError will be raised if dumping field is missing.
# Field will be excluded from load result if loading field is missing.
missing = _Missing()


def no_processing(value):
    return value


def snake_to_camel(snake: str) -> str:
    camel = snake.title().replace('_', '')
    if camel:
        camel = camel[0].lower() + camel[1:]
    return camel


def ensure_staticmethod(func: Callable) -> staticmethod:
    if isinstance(func, staticmethod):
        return func
    return staticmethod(func)
