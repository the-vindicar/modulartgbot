"""Реализует простой загрузчик конфигов, извлекающий их содержимое из YAML-файлов."""
import dataclasses
from pathlib import Path
import typing as t

import pydantic
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
            type_adapter = pydantic.TypeAdapter(configclass)
            return type_adapter.validate_python(data)

    async def save(self, name: str, config: _T) -> None:
        data = dataclasses.asdict(config)
        with (self.config_path / f'{name}.yaml').open('wt', encoding='utf-8') as cfg:
            yaml.dump(data, cfg, indent=4, allow_unicode=True, sort_keys=False, width=160)
