"""Автоматически строит форму с настройками для сущности."""
import typing as t
import datetime
from html import escape
import pydantic


__all__ = [
    'FormPattern', 'DIV_PATTERN', 'TABLE_PATTERN',
    'model2fields'
]
TModel = t.TypeVar('TModel')


class FormPattern(t.NamedTuple):
    """Набор строк, определяющий, как отдельные поля ввода комбинируются в структуры.
    Ключ {name} соответствует имени поля, ключ {caption} - видимому заголовку поля, а ключ {input} - разметке поля.
    Будьте осторожны и не забывайте, что name и caption должны экранироваться перед подстановкой в строку."""
    primitive: str
    compound: str


DIV_PATTERN = FormPattern(
    primitive='<div class="field"><label for="{name}">{caption}</label>\n{input}</div>\n',
    compound='<section><div class="section">{caption}</div>\n{input}\n</section>\n',
)


TABLE_PATTERN = FormPattern(
    primitive='<tr><td class="field"><label for="{name}">{caption}</label></td>\n<td>{input}</td></tr>\n',
    compound='<tr><td class="section" colspan="2"><section>{caption}<br/>\n{input}\n</section></td></tr>\n',
)


def model2fields(model: TModel, pattern: FormPattern = None, toplevelcaption: str = None) -> str:
    """
    Формирует набор полей для HTML-формы, соответствующий указанной модели.
    Если для класса модели требуется нестандартная генерация, определите в классе следующий метод::

        def generate_fields (self, name: str, optional: bool, caption: str | None, pattern: FormPattern) -> str:

    Где параметр name определяет префикс имени для объекта self (используется в именах полей формы),
    параметр optional указывает, является ли данный набор полей обязательным,
    параметр caption содержит предпочитаемый отображаемый заголовок для  набора полей,
    а параметр pattern содержит строки, которые позволят скомпоновать отдельные наборы таблиц в единую форму.
    """
    ta = pydantic.TypeAdapter(type(model))
    schema = ta.json_schema()
    # import pprint
    # pprint.pprint(schema)
    return schema2fields(schema, '', model, pattern, toplevelcaption)


def schema2fields(schema: dict[str, t.Any], name: str, value: t.Any,
                  pattern: FormPattern = None, toplevelcaption: str = None, defs: dict[str, t.Any] = None) -> str:
    """Подготавливает набор полей на основании схемы."""
    if defs is None:
        defs = schema.get('$defs', {})
    if pattern is None:
        pattern = DIV_PATTERN
    optional, stype = schema2type(schema)
    caption = next((c for c in [
        toplevelcaption,
        schema.get('description', None),
        getattr(type(value), '__doc__', None) if stype == 'object' else None,
        schema.get('title', None),
        name
    ] if c), '')

    if callable(getattr(value, 'generate_fields', None)):  # у этого класса есть метод generate_fields(), вызываем его
        return value.generate_fields(name, optional, caption, pattern)

    if stype == 'object':
        parts = []
        props = schema['properties']
        for item, itemschema in props.items():
            try:
                itemname = f'{name}[{item}]' if name else item
                itemvalue = getattr(value, item)
                itemcaption = itemschema.get('description', None)
                if '$ref' in itemschema:
                    itempath: str = itemschema['$ref']
                    itempath = itempath[len('#/$defs/'):]
                    itemschema = defs[itempath]
                    if itemcaption is None:
                        itemcaption = itemschema.get('description', None)
                part = schema2fields(itemschema, itemname, itemvalue, pattern, itemcaption, defs)
            except Exception as err:
                print(err)
            else:
                parts.append(part)
        return pattern.compound.format(name=name, caption=caption, input='\n'.join(parts))
    if stype == 'integer':
        input_code = schema2field_int(schema, name, optional, value)
    elif stype == 'number':
        input_code = schema2field_float(schema, name, optional, value)
    elif stype == 'boolean':
        input_code = schema2field_bool(schema, name, optional, value)
    elif stype != 'string':
        raise TypeError(f'Unsupported type: {stype}')
    else:
        fmt = schema.get('format', '')
        if fmt == '':
            if 'enum' in schema:
                input_code = schema2field_enum(schema, name, optional, value)
            else:
                input_code = schema2field_str(schema, name, optional, value)
        elif fmt == 'textarea':
            input_code = schema2field_text(schema, name, optional, value)
        elif fmt == 'date-time':
            input_code = schema2field_datetime(schema, name, optional, value)
        elif fmt == 'duration':
            input_code = schema2field_timedelta(schema, name, optional, value)
        elif fmt == 'email':
            input_code = schema2field_email(schema, name, optional, value)
        elif fmt == 'uri':
            input_code = schema2field_uri(schema, name, optional, value)
        else:
            raise TypeError(f'Unsupported format: {fmt}')
    return pattern.primitive.format(input=input_code, caption=escape(caption), name=escape(name))


def schema2field_enum(schema: dict[str, t.Any], name: str, optional: bool, value: t.Optional[str]) -> str:
    """Формирует поле ввода перечисления."""
    attrs = [f'name="{escape(name)}"', f'id="{escape(name)}"', 'size="1"']
    options = [
        f'<option {"selected" if value == v else ""}>{escape(v)}</option>'
        for v in schema['enum']
    ]
    if optional:
        options.insert(0, f'<option {"selected" if value is None else ""} value="">---</option>')
    else:
        attrs.append('required')
    return f'<select {" ".join(attrs)}>{"".join(options)}</select>'


def schema2field_uri(_schema: dict[str, t.Any], name: str, optional: bool, value: t.Optional[str]) -> str:
    """Формирует поле ввода URL."""
    attrs = ['type="url"', f'name="{escape(name)}"', f'id="{escape(name)}"']
    if not optional:
        attrs.append('required')
    value = str(value) if value is not None else ''
    attrs.append(f'value="{escape(value)}"')
    return f'<input {" ".join(attrs)}/>'


def schema2field_email(_schema: dict[str, t.Any], name: str, optional: bool, value: t.Optional[str]) -> str:
    """Формирует поле ввода почтового адреса."""
    attrs = ['type="email"', f'name="{escape(name)}"', f'id="{escape(name)}"']
    if not optional:
        attrs.append('required')
    value = str(value) if value is not None else ''
    attrs.append(f'value="{escape(value)}"')
    return f'<input {" ".join(attrs)}/>'


def schema2field_timedelta(
        _schema: dict[str, t.Any], name: str, optional: bool, value: t.Optional[datetime.timedelta]) -> str:
    """Формирует поле ввода интервала времени."""
    attrs = [
        'type="text"', f'name="{escape(name)}"', f'id="{escape(name)}"',
        r'pattern="\s*(\d+\s*[дd]\w*\s*)?\d+:\d+(:\d+(.\d+)?)?\s*"',
        'title="Пример: 3 д 12:34:56"'
    ]
    if not optional:
        attrs.append('required')
    if value is not None:
        svalue = f'{value.days} д ' if value.days != 0 else ''
        svalue += f'{value.seconds // 3600:02d}:{(value.seconds % 3600) // 60:02d}:{value.seconds % 60:02d}'
        svalue += f'.{value.microseconds:06d}' if value.microseconds > 0 else ''
        value = svalue
    else:
        value = ''
    attrs.append(f'value="{value}"')
    return f'<input {" ".join(attrs)}/>'


def schema2field_datetime(_schema: dict[str, t.Any], name: str, optional: bool, value: t.Optional[datetime.datetime]
                          ) -> str:
    """Формирует поле ввода даты-времени."""
    attrs = ['type="datetime-local"', f'name="{escape(name)}"', f'id="{escape(name)}"']
    if not optional:
        attrs.append('required')
    value = value.isoformat(timespec='seconds') if value is not None else ''
    attrs.append(f'value="{value}"')
    return f'<input {" ".join(attrs)}/>'


def schema2field_text(schema: dict[str, t.Any], name: str, _optional: bool, value: t.Optional[bool]) -> str:
    """Формирует поле ввода многострочного текста."""
    attrs = [f'name="{escape(name)}"', f'id="{escape(name)}"']
    if 'examples' in schema:
        ex = '; '.join(map(str, schema['examples']))
        attrs.append(f'title="{escape(ex)}"')
    if 'minLength' in schema:
        attrs.append(f'minlength="{int(schema["minLength"])}"')
    if 'maxLength' in schema:
        attrs.append(f'maxlength="{int(schema["maxLength"])}"')
    value = str(value) if value is not None else ''
    return f'<textarea {" ".join(attrs)}>{escape(value)}</textarea>'


def schema2field_str(schema: dict[str, t.Any], name: str, optional: bool, value: t.Optional[bool]) -> str:
    """Формирует поле ввода обычной строки."""
    attrs = ['type="text"', f'name="{escape(name)}"', f'id="{escape(name)}"']
    if 'examples' in schema:
        ex = '; '.join(map(str, schema['examples']))
        attrs.append(f'title="{escape(ex)}"')
    if 'minLength' in schema:
        attrs.append(f'minlength="{int(schema["minLength"])}"')
    if 'maxLength' in schema:
        attrs.append(f'maxlength="{int(schema["maxLength"])}"')
    if 'pattern' in schema:
        attrs.append(f'pattern="{escape(schema["pattern"])}"')
    if not optional:
        attrs.append('required')
    value = str(value) if value is not None else ''
    attrs.append(f'value="{escape(value)}"')
    return f'<input {" ".join(attrs)}/>'


def schema2field_bool(_schema: dict[str, t.Any], name: str, optional: bool, value: t.Optional[bool]) -> str:
    """Формирует поле ввода логического значения."""
    attrs = [f'name="{escape(name)}"', f'id="{escape(name)}"', 'size="1"']
    options = [
        f'<option {"selected" if bool(value) else ""} value="1">Да</option>',
        f'<option {"selected" if value is not None and not bool(value) else ""} value="0">Нет</option>',
    ]
    if optional:
        options.insert(0, f'<option {"selected" if value is None else ""} value="null">---</option>')
    else:
        attrs.append('required')
    return f'<select {" ".join(attrs)}>{"".join(options)}</select>'


def schema2field_float(schema: dict[str, t.Any], name: str, optional: bool, value: t.Optional[float]) -> str:
    """Формирует поле ввода дробного числа."""
    attrs = ['type="number"', f'name="{escape(name)}"', f'id="{escape(name)}"']
    if 'minimum' in schema:
        attrs.append(f'min="{schema["minimum"]}"')
    elif 'exclusiveMinimum' in schema:
        emin = schema["exclusiveMinimum"]
        attrs.append(f'min="{emin * 1.000001 if emin > 0 else emin * 0.999999 if emin < 0 else 0.000001}"')
    if 'maximum' in schema:
        attrs.append(f'max="{schema["maximum"]}"')
    elif 'exclusiveMaximum' in schema:
        emax = schema["exclusiveMaximum"]
        attrs.append(f'max="{emax * 1.000001 if emax < 0 else emax * 0.999999 if emax > 0 else -0.000001}"')
    if not optional:
        attrs.append('required')
    value = float(value) if value is not None else ''
    attrs.append(f'value="{value}"')
    return f'<input {" ".join(attrs)}/>'


def schema2field_int(schema: dict[str, t.Any], name: str, optional: bool, value: t.Optional[int]) -> str:
    """Формирует поле ввода целого числа."""
    attrs = ['type="number"', f'name="{escape(name)}"', f'id="{escape(name)}"', 'step="1"']
    if 'minimum' in schema:
        attrs.append(f'min="{schema["minimum"]}"')
    elif 'exclusiveMinimum' in schema:
        attrs.append(f'min="{schema["exclusiveMinimum"] + 1}"')
    if 'maximum' in schema:
        attrs.append(f'max="{schema["maximum"]}"')
    elif 'exclusiveMaximum' in schema:
        attrs.append(f'max="{schema["exclusiveMaximum"] - 1}"')
    if not optional:
        attrs.append('required')
    value = int(value) if value is not None else ''
    attrs.append(f'value="{value}"')
    return f'<input {" ".join(attrs)}/>'


def schema2type(schema: dict[str, t.Any]) -> tuple[bool, str]:
    """Определяет тип данных поля."""
    optional = False
    if 'type' in schema:
        stype = schema['type']
    elif 'anyOf' in schema:
        options: list[dict[str, t.Any]] = schema['anyOf']
        for opt in options:
            if opt['type'] == 'null':
                optional = True
                options.remove(opt)
                break
        if len(options) == 1:
            stype = options[0]['type']
        else:
            raise TypeError('Unions are not supported, sorry!')
    else:
        raise TypeError('No type information')
    return optional, stype
