"""Реализует простой загрузчик конфигов, извлекающий их содержимое из YAML-файлов."""
import dataclasses
from pathlib import Path
import typing as t

import yaml

from ._protocols import ConfigManager


__all__ = ['ConfigManagerImpl']
_T = t.TypeVar('_T')


class ConfigManagerImpl(ConfigManager):
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config_path.mkdir(parents=True, exist_ok=True)

    async def load(self, name: str, configclass: t.Type[_T]) -> _T:
        try:
            with (self.config_path / f'{name}.yaml').open('rt', encoding='utf-8-sig') as cfg:
                data = yaml.safe_load(cfg)
        except IOError:
            try:
                default = configclass()
            except Exception:
                raise RuntimeError(f'Config "{name}" does not exist, and config class "{configclass.__qualname__}" '
                                   f'does not provide all default values')
            else:
                await self.save(name, default)
                return default
        else:
            return self.construct_instance(configclass, data)

    async def save(self, name: str, config: _T) -> None:
        data = dataclasses.asdict(config)
        with (self.config_path / f'{name}.yaml').open('wt', encoding='utf-8') as cfg:
            yaml.dump(data, cfg, indent=4, allow_unicode=True, sort_keys=False, width=160)

    @staticmethod
    def _subclasscheck(klass: t.Type, parents: t.Union[t.Type, t.Iterable[t.Type]]) -> bool:
        try:
            return issubclass(klass, parents)
        except TypeError:
            return False

    @classmethod
    def construct_instance(cls, configclass: t.Type[_T], data: dict[str, t.Any]) -> _T:
        """Конструирует экземпляр переданного датакласса на основании переданных данных."""
        values: dict[str, t.Any] = {}
        for field in dataclasses.fields(configclass):
            base = t.get_origin(field.type)
            if field.name not in data:
                if (field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING and
                        base is t.Union and None in t.get_args(field.type)):
                    values[field.name] = None
            elif base is None:
                if dataclasses.is_dataclass(field.type):
                    values[field.name] = cls.construct_instance(field.type, data[field.name])
                else:
                    values[field.name] = data[field.name]
            elif cls._subclasscheck(base, t.Iterable):
                element = t.get_args(field.type)
                collection = data[field.name]
                if isinstance(collection, t.Iterable) and not isinstance(collection, str):
                    if element and dataclasses.is_dataclass(element[0]):
                        eletype = element[0]
                        values[field.name] = base([cls.construct_instance(eletype, item) for item in collection])
                    else:
                        values[field.name] = base(collection)
            else:
                values[field.name] = data[field.name]
        return configclass(**values)
