import inspect

from typing import Dict, Iterable, Callable, Sequence, Any, Tuple
from functools import wraps, partial
from collections import OrderedDict

from .fields import Field, NestedField
from .exceptions import ValidationError
from .utils import (
    missing, no_processing,
    assign_attr_or_item_getter, assign_item_getter,
    LoadResult, DumpResult, CatalystResult, OptionBox
)


FieldDict = Dict[str, Field]


class BaseCatalyst:
    _field_dict = {}  # type: FieldDict

    class Options(OptionBox):
        dump_method = 'format'
        load_method = 'load'

        raise_error = False
        all_errors = True
        schema = None

    # assign getter for dumping & loading
    _assign_dump_getter = staticmethod(assign_attr_or_item_getter)
    _assign_load_getter = staticmethod(assign_item_getter)

    @staticmethod
    def _format_field_key(key):
        return key

    @staticmethod
    def _format_field_name(name):
        return name

    @staticmethod
    def _copy_fields(
            fields: FieldDict, keys: Iterable[str],
            is_copying: Callable[[str], bool]) -> FieldDict:
        new_fields = {}  # type: FieldDict
        for key in keys:
            if is_copying(key):
                new_fields[key] = fields[key]
        return new_fields

    @staticmethod
    def _set_fields(cls_or_obj, attrs):
        raise NotImplementedError()

    def __init__(
            self,
            schema: Any = None,
            fields: Iterable[str] = None,
            raise_error: bool = None,
            all_errors: bool = None,
            dump_fields: Iterable[str] = None,
            dump_method: str = None,
            load_fields: Iterable[str] = None,
            load_method: str = None,
            **kwargs):
        # set fields from a non `Catalyst` class, which can avoid override
        if schema:
            attrs = ((attr, getattr(schema, attr)) for attr in dir(schema))
            self._set_fields(self, attrs)

        if not fields:
            fields = set(self._field_dict.keys())
        if not dump_fields:
            dump_fields = fields
        if not load_fields:
            load_fields = fields

        self._dump_field_dict = self._copy_fields(
            self._field_dict, dump_fields,
            lambda k: not self._field_dict[k].opts.no_dump)

        self._load_field_dict = self._copy_fields(
            self._field_dict, load_fields,
            lambda k: not self._field_dict[k].opts.no_load)

        self.opts = self.Options(
            schema=schema,
            raise_error=raise_error,
            all_errors=all_errors,
            dump_method=dump_method,
            load_method=load_method,
            **kwargs,
        )

        if self.opts.dump_method not in {'dump', 'format', 'validate'}:
            raise ValueError("Argument `method` must be in ('dump', 'format', 'validate').")

        if self.opts.load_method not in {'load', 'parse', 'validate'}:
            raise ValueError("Argument `method` must be in ('load', 'parse', 'validate').")

    def __repr__(self):
        args = []
        schema = self.opts.schema
        if schema:
            if isinstance(schema, type):
                schema = self.opts.schema.__name__
            else:
                schema = self.opts.schema.__class__.__name__
            args.append(f'schema={schema}')
        args.append(f'raise_error={self.opts.raise_error}')
        args.append(f'all_errors={self.opts.all_errors}')
        args = ', '.join(args)
        return f'<{self.__class__.__name__}({args})>'

    def _side_effect(self, name: str, data: Any):
        """Do side effect before or after processs.

        :param name: The name of side effect method, which named with
            prefix and method name, such as `pre_dump` or `post_dump_many`.
            There are two words `pre` and `post` can be used to
            prefix four methods `dump`, `load`, `dump_many`, `load_many`.
        """
        handle = getattr(self, name, no_processing)
        try:
            valid_data = handle(data)
            invalid_data = None
            errors = None
        except Exception as e:
            error_key = getattr(handle, 'error_key', name)
            errors = {error_key: e}
            invalid_data = data
            valid_data = None
        return valid_data, errors, invalid_data

    def _process_flow(
            self,
            name: str,
            many: bool,
            data: Any,
            raise_error: bool = None,
            all_errors: bool = None,
        ) -> CatalystResult:
        """Core basic process flow.
        """
        if name == 'dump':
            ResultClass = DumpResult
        elif name == 'load':
            ResultClass = LoadResult
        else:
            raise ValueError("Argument `name` must be `dump` or `load`.")

        # select data handle
        if many:
            method_name = f'{name}_many'
            handle = self._process_many
        else:
            method_name = name
            handle = self._process_one

        all_errors = self.opts.get(all_errors=all_errors)
        raise_error = self.opts.get(raise_error=raise_error)

        valid_data, errors, invalid_data = self._side_effect(f'pre_{method_name}', data)

        if not errors:
            valid_data, errors, invalid_data = handle(name, valid_data, all_errors)

        if not errors:
            valid_data, errors, invalid_data = self._side_effect(f'post_{method_name}', valid_data)

        result = ResultClass(valid_data, errors, invalid_data)
        if errors and raise_error:
            raise ValidationError(result)
        return result

    def _process_one(self, name: str, data: Any, all_errors: bool):
        if name == 'dump':
            source_attr = 'name'
            target_attr = 'key'
            field_dict = self._dump_field_dict  # type: FieldDict
            assign_getter = self._assign_dump_getter
            method = self.opts.dump_method
        elif name == 'load':
            source_attr = 'key'
            target_attr = 'name'
            field_dict = self._load_field_dict  # type: FieldDict
            assign_getter = self._assign_load_getter
            method = self.opts.load_method
        else:
            raise ValueError("Argument `name` must be 'dump' or 'load'.")

        # According to the type of `data`, assign a function to get field value from `data`
        get_value = assign_getter(data)

        valid_data, errors, invalid_data = {}, {}, {}

        for field in field_dict.values():
            required = getattr(field.opts, f'{name}_required')
            default = getattr(field, f'{name}_default')
            source = getattr(field, source_attr)
            target = getattr(field, target_attr)

            raw_value = get_value(data, source, default)
            try:
                # if the field's value is missing
                # raise error if required otherwise skip
                if raw_value is missing:
                    if required:
                        errors[source] = field.get_error('required')
                        if not all_errors:
                            break
                    continue

                valid_data[target] = getattr(field, method)(raw_value)
            except Exception as e:
                # collect errors and invalid data
                if isinstance(e, ValidationError) and isinstance(e.msg, CatalystResult):
                    # distribute nested data in CatalystResult
                    valid_data[target] = e.msg.valid_data
                    errors[source] = e.msg.errors
                    invalid_data[source] = e.msg.invalid_data
                else:
                    errors[source] = e
                    invalid_data[source] = raw_value
                if not all_errors:
                    break

        return valid_data, errors, invalid_data

    def _process_many(self, name: str, data: Sequence, all_errors: bool):
        valid_data, errors, invalid_data = [], OrderedDict(), OrderedDict()
        for i, item in enumerate(data):
            result = self._process_flow(name, False, item, False, all_errors)
            valid_data.append(result.valid_data)
            if not result.is_valid:
                errors[i] = result.errors
                invalid_data[i] = result.invalid_data
                if not all_errors:
                    break
        return valid_data, errors, invalid_data

    def _process_args(
            self, func: Callable = None, name: str = None, all_errors: bool = None,
        ) -> Callable:
        """Decorator for handling args by catalyst before function is called.
        The wrapper function takes args as same as args of the raw function.
        If args are invalid, error will be raised. In general, `*args` should
        be handled by ListField, and `**kwargs` should be handled by NestedField.
        """
        if func:
            sig = inspect.signature(func)
            @wraps(func)
            def wrapper(*args, **kwargs):
                ba = sig.bind(*args, **kwargs)
                result = self._process_flow(name, False, ba.arguments, True, all_errors)
                ba.arguments.update(result.valid_data)
                return func(*ba.args, **ba.kwargs)
            return wrapper
        return partial(self._process_args, name=name, all_errors=all_errors)

    def dump(
            self,
            data: Any,
            raise_error: bool = None,
            all_errors: bool = None,
        ) -> DumpResult:
        return self._process_flow('dump', False, data, raise_error, all_errors)

    def load(
            self,
            data: Any,
            raise_error: bool = None,
            all_errors: bool = None,
        ) -> LoadResult:
        return self._process_flow('load', False, data, raise_error, all_errors)

    def dump_many(
            self,
            data: Sequence,
            raise_error: bool = None,
            all_errors: bool = None,
        ) -> DumpResult:
        return self._process_flow('dump', True, data, raise_error, all_errors)

    def load_many(
            self,
            data: Sequence,
            raise_error: bool = None,
            all_errors: bool = None,
        ) -> LoadResult:
        return self._process_flow('load', True, data, raise_error, all_errors)

    def dump_args(self, func: Callable = None, all_errors: bool = None) -> Callable:
        return self._process_args(func, 'dump', all_errors)

    def load_args(self, func: Callable = None, all_errors: bool = None) -> Callable:
        return self._process_args(func, 'load', all_errors)

    def pre_dump(self, data):
        return data
    pre_dump.error_key = 'pre_dump'

    def post_dump(self, data):
        return data
    post_dump.error_key = 'post_dump'

    def pre_load(self, data):
        return data
    pre_load.error_key = 'pre_load'

    def post_load(self, data):
        return data
    post_load.error_key = 'post_load'

    def pre_dump_many(self, data):
        return data
    pre_dump_many.error_key = 'pre_dump_many'

    def post_dump_many(self, data):
        return data
    post_dump_many.error_key = 'post_dump_many'

    def pre_load_many(self, data):
        return data
    pre_load_many.error_key = 'pre_load_many'

    def post_load_many(self, data):
        return data
    post_load_many.error_key = 'post_load_many'


class CatalystMeta(type):
    """Metaclass for `Catalyst` class. Binds fields to `_field_dict` attribute."""

    def __new__(cls, name, bases, attrs):
        new_cls = type.__new__(cls, name, bases, attrs)
        new_cls._set_fields(new_cls, attrs.items())
        return new_cls


class Catalyst(BaseCatalyst, metaclass=CatalystMeta):
    __doc__ = BaseCatalyst.__doc__

    @staticmethod
    def _set_fields(cls_or_obj: BaseCatalyst, attrs: Iterable[Tuple[str, Any]]):
        """Set fields for `Catalyst` class or its instance.
        Fields are bond to `cls_or_obj._field_dict` which are set separately
        on class or its instance, which works like class inheritance.

        :param cls_or_obj: `Catalyst` class or its instance
        :param attrs: iterable which contains name, field pairs
            [(name, Field), ...]
        """
        fields = {}  # type: FieldDict
        # inherit fields
        fields.update(cls_or_obj._field_dict)

        for attr, value in attrs:
            # init calalyst object
            if isinstance(value, CatalystMeta):
                value = value()
            # wrap catalyst object as NestedField
            if isinstance(value, BaseCatalyst):
                value = NestedField(value)
            # automatic generate field name or key
            if isinstance(value, Field):
                if value.name is None:
                    value.name = cls_or_obj._format_field_name(attr)
                if value.key is None:
                    value.key = cls_or_obj._format_field_key(attr)

                fields[attr] = value

        cls_or_obj._field_dict = fields
