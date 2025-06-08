import datetime
import typing as tp

__all__ = ['MoodleFunctions']

if tp.TYPE_CHECKING:
    from ._moodle import Moodle


class MoodleFuncWrapper(tp.Protocol):
    async def __call__(self, **kwargs) -> tp.Union[tp.List, tp.Dict[str, tp.Any]]:
        ...


class MoodleFunctions:
    """Этот класс служит пространством имён для вызова функций Moodle Web API.
    При обращении к атрибуту класса будет создан объект-обёртка, вызывающий одноименную функцию."""
    __slots__ = ('__owner', )

    def __init__(self, owner: 'Moodle'):
        self.__owner = owner

    def __getattr__(self, item: str) -> MoodleFuncWrapper:
        """При обращении к неизвестному атрибуту класса создаётся объект-обёртка, вызывающий одноименную функцию."""
        async def wrapper(**kwargs):
            return await self(func=item, kwargs=kwargs)
        wrapper.__name__ = item
        return wrapper  # noqa

    def transform_param(self, name: str, value: tp.Any) -> dict[str, tp.Any]:
        """Выполняет преобразование параметров вызываемой функции в форму, пригодную для передачи в URL.
        :param name: Имя параметра. Служит основой для параметров-массивов и параметров-словарей.
        :param value: Значение параметра. Его тип определяет характер преобразования.
        :returns: Набор имён и значений примитивных параметров, которые следует подставить в URL."""
        if isinstance(value, (tuple, list, set, frozenset)):
            # линейные коллекции используют синтаксис param[0]=value0&param[1]=value1&...
            result = {}
            for i, val in enumerate(value):
                result.update(self.transform_param(f'{name}[{i}]', val))  # значения преобразуем рекурсивно
            return result
        elif isinstance(value, dict):
            # словари используют синтаксис param[key0]=value0&param[key1]=value1&...
            result = {}
            for key, val in value.items():
                result.update(self.transform_param(f'{name}[{key}]', val))  # значения преобразуем рекурсивно
            return result
        elif isinstance(value, datetime.datetime):
            # дата и время преобразуется в часовой пояс сервера, а потом в int
            return {name: int(value.astimezone(self.__owner.timezone).timestamp())}
        elif isinstance(value, (int, float, str)):
            # примитивные типы данные передаются как есть
            return {name: value}
        else:
            # мы не знаем, как поступать с остальным
            raise TypeError(f'Unsupported type for parameter {name!r}: {type(value)!r}')

    async def __call__(self, func: str, kwargs: tp.Dict[str, tp.Any]
                       ) -> tp.Union[tp.List, tp.Dict[str, tp.Any]]:
        """Вызываем указанную функцию Moodle Web API.
        :param func: Имя функции, например, 'core_webservice_get_site_info'.
        :param kwargs: Аргументы, передаваемые функции.
        :returns: Ответ сервера, декодированный из JSON."""
        params = {}
        for name, value in kwargs.items():
            params.update(self.transform_param(name, value))
        params.update({
            'wsfunction': func,
            'wstoken': self.__owner.token,
            'moodlewsrestformat': 'json'
        })
        result = await self.__owner.query('webservice/rest/server.php', params=params)
        return result
