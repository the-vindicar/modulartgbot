"""Описывает протоколы взаимодействия между системой и модулями, предоставляет ряд инструментов для реализации модулей,
а также предоставляет загрузчик модулей и базовый конфигуратор модулей."""
from ._protocols import *
from ._loader import modules_lifespan
from ._tools import *
from ._config_manager import ConfigManagerImpl
from ._logs import setup_logging
from _quart_hax import *
