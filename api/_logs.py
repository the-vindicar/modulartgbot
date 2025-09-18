"""Отвечает за конфигурирование журнала работы системы, и реализацию желаемого поведения при записи ошибок."""
import typing as t
import dataclasses
import logging
import logging.handlers
import os
import sys
import sysconfig
import site
import types
import traceback

import quart
import quart.logging

from ._protocols import ConfigManager


__all__ = ['setup_logging']


class ReducedTracebackFormatter(logging.Formatter):
    """Этот форматтер убирает из лога все фреймы, которые не относятся к основному коду программы.
    А именно, он прячет стандартную библиотеку языка, установленные пакеты, а также содержимое того модуля,
    где определён он сам.
    Остальные фреймы форматируются и выводятся как обычно."""
    STDLIB = sysconfig.get_paths().get('stdlib', None)
    SITEPACKAGES = site.getsitepackages()
    API_PATH = os.path.dirname(__file__)
    IGNORED = [STDLIB, *SITEPACKAGES, API_PATH]

    def formatException(self, ei: tuple[t.Type[Exception], Exception, types.TracebackType]) -> str:
        """Формирует строку с информацией об исключении."""
        etype, evalue, tb_root = ei
        tb = tb_root
        frames = []
        while tb is not None:  # перебираем все фреймы в трейсбэке
            filename = tb.tb_frame.f_code.co_filename  # к какому файлу относится фрейм?
            if not any(filename.startswith(p) for p in self.IGNORED if p):  # если файл из НЕ игнорируемых каталогов
                frames.append(tb)  # мы учтём этот фрейм
            tb = tb.tb_next
        formats = []
        for tb in frames:  # форматируем все учтённые фреймы
            formats.extend(traceback.format_tb(tb, 1))
        formatted_tb = ''.join(formats)
        return f'{etype.__name__}: {evalue}\n{formatted_tb}'


@dataclasses.dataclass
class LoggingCfg:
    """Конфигурация журнала работы системы."""
    file: str = None
    file_maxsize: int = 1024*1024
    file_backups: int = 3
    file_level: str = 'DEBUG'
    stderr_level: str = 'DEBUG'
    reduced_stacktraces: bool = True
    levels: dict[str, str] = dataclasses.field(default_factory=dict)


async def setup_logging(cfg: ConfigManager, app: quart.Quart):
    """Подготавливает и настраивает журнал работы системы, удостоверяясь,
     что все записи идут только через наши обработчики."""
    logcfg = await cfg.load('logging', LoggingCfg)
    applog = logging.getLogger(app.name)
    applog.removeHandler(quart.logging.default_handler)
    logging.root.handlers.clear()
    # определяем обработчик для непойманных исключений
    sys.excepthook = lambda et, ev, etb: logging.root.critical('Uncaught exception:', exc_info=(et, ev, etb))
    formatter_class = ReducedTracebackFormatter if logcfg.reduced_stacktraces else logging.Formatter

    conformatter = formatter_class(fmt='%(asctime)s [%(levelname)8s] %(name)s@%(process)d: %(message)s')
    fileformatter = formatter_class(fmt='%(asctime)s [%(levelname)8s] %(name)s@%(process)d: %(message)s')

    chandler = logging.StreamHandler()
    chandler.setFormatter(conformatter)
    chandler.setLevel(logging.DEBUG)
    logging.root.addHandler(chandler)
    if logcfg.file:
        fhandler = logging.handlers.RotatingFileHandler(
            filename=logcfg.file,
            encoding='utf-8',
            maxBytes=logcfg.file_maxsize,
            backupCount=logcfg.file_backups
        )
        fhandler.setLevel(logcfg.file_level)
        fhandler.setFormatter(fileformatter)
        logging.root.addHandler(fhandler)
    for logname, level in logcfg.levels.items():
        logging.getLogger(logname).setLevel(level)
