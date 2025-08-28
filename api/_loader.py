"""Содержит классы, реализующие обнаружение, загрузку и сопровождение модулей."""
import contextlib
import dataclasses
import importlib
import sys
from pathlib import Path
import logging
from typing import (cast, final, Optional, Container, Coroutine, AsyncGenerator,
                    Callable, Type, ClassVar, TypeVar, Union, Any)

import quart

from ._protocols import CoreAPI, PluginAPI, ConfigManager, PostInit


__all__ = ['modules_lifespan']
_T = TypeVar('_T')


@dataclasses.dataclass(frozen=True)
class BotCoreAPIImpl(CoreAPI):
    config: ConfigManager
    register_api_provider: Callable
    get_api_provider: Callable
    register_web_router: Callable

    async def __call__(self, item: Type[_T]) -> _T:
        provider = self.get_api_provider(item)
        return await provider()


@final
@dataclasses.dataclass(slots=True)
class LoadedModule:
    """Описывает загруженный модуль."""
    MODULES_DIR: ClassVar[str] = 'modules'
    name: str
    requires: frozenset[Type]
    provides: frozenset[Type]
    lifetime: Callable[[CoreAPI], AsyncGenerator]
    api: BotCoreAPIImpl
    context: Optional[AsyncGenerator]
    has_post_init: Optional[bool]

    @staticmethod
    def load_from(mod_name: str, api: BotCoreAPIImpl) -> 'LoadedModule':
        """Загружает модуль по имени, запоминая ссылку на API, которую он будет использовать."""
        module: PluginAPI = cast(PluginAPI, importlib.import_module(f'{LoadedModule.MODULES_DIR}.{mod_name}'))
        requires = frozenset(getattr(module, 'requires', None) or tuple())
        provides = frozenset(getattr(module, 'provides', None) or tuple())
        return LoadedModule(
            name=mod_name,
            requires=requires,
            provides=provides,
            lifetime=module.lifetime,
            api=api,
            context=None,
            has_post_init=None
        )

    @staticmethod
    def sort_dependencies(loaded: list['LoadedModule']) -> None:
        """Сортирует список модулей так, чтобы зависимые модули были загружены после своих зависимостей."""
        available: set[Union[Type, str]] = {quart.Quart}
        ordered: list['LoadedModule'] = []
        unordered = loaded.copy()
        while unordered:
            added_any = False
            for i in range(len(unordered)-1, -1, -1):
                if available.issuperset(unordered[i].requires):  # есть всё, что нужно для запуска модуля?
                    ordered.append(unordered[i])
                    available.update(unordered[i].provides)
                    available.add(unordered[i].name)
                    del unordered[i]
                    added_any = True
            if not added_any:  # ни один из оставшихся модулей нельзя запустить!
                unmet = []
                for m in unordered:
                    missing = ', '.join(t.__qualname__ for t in (set(m.requires) - available))
                    unmet.append(f'{m.name} ({missing})')
                raise ValueError(f'Modules with unmet dependencies: {"; ".join(unmet)}')
        loaded[:] = ordered

    async def enter_context(self) -> None:
        """Входит в контекст модуля, выполняя его инициализацию."""
        if self.context is None:
            self.context = self.lifetime(self.api)
            value = await self.context.__anext__()
            self.has_post_init = value is PostInit

    async def run_post_init(self) -> None:
        """Если модуль требует пост-инициализацию, мы позволяем её выполнить. Иначе мы не делаем ничего."""
        if self.context is not None and self.has_post_init:
            await self.context.__anext__()

    async def exit_context(self) -> None:
        """Покидает контекст модуля, позволяя ему освободить ресурсы и корректно завершить работу."""
        if self.context is not None:
            self.context, ctx = None, self.context
            await ctx.__anext__()


@contextlib.asynccontextmanager
async def modules_lifespan(
        webapp: quart.Quart,
        cfg: ConfigManager,
        *, module_whitelist: Container[str] = None
        ):
    """Основной менджер контекста, отвечающий за запуск, сопровождение и остановку модулей.
    :param webapp: Основное приложение (веб-сервер). Используется для регистрации blueprint'ов.
    :param cfg: Менеджер конфигурации. Передаётся модулям для загрузки их конфигов.
    :param module_whitelist: Белый список модулей для загрузки. Если пуст, то будут загружены все обнаруженные модули.
    """
    log = logging.getLogger('modules')
    module_api_providers: dict[Type[_T], Coroutine[Any, Any, _T]] = {}

    def get_api(api_class: Type[_T]) -> Coroutine[Any, Any, _T]:
        """Реализация, позволяющая получить провайдера для указанной зависимости."""
        return module_api_providers[api_class]

    def add_api(api_provider: Union[Coroutine[Any, Any, _T], _T], api_class: Type[_T]) -> None:
        """Реализация, позволяющая зарегистрировать провайдера для предоставляемой зависимости."""
        if api_class in module_api_providers:
            raise KeyError(f'API {api_class.__name__} has already been provided.')
        if isinstance(api_provider, api_class):  # если нам передали объект, мы просто всегда возвращаем его.
            async def provider() -> _T:
                """Возвращает экземпляр класса."""
                return api_provider

            module_api_providers[api_class] = provider  # type: ignore
        else:  # если нам передали корутину, мы будем вызывать её для получения зависимости
            module_api_providers[api_class] = api_provider

    def register_web_blueprint(blueprint):
        """Реализация, позволяющая зарегистрировать blueprint для веб-сервера."""
        webapp.register_blueprint(blueprint)

    add_api(webapp, quart.Quart)
    # находим и загружаем модули
    loaded_modules = []
    moddir = Path(sys.argv[0]).parent / LoadedModule.MODULES_DIR
    log.debug('Searching for modules in %s ...', moddir)
    for item in moddir.glob('*'):
        mod_name = item.stem
        if item.name.startswith(('_', '.')) or (module_whitelist is not None and mod_name not in module_whitelist):
            continue
        if (item.is_file() and item.name.endswith('.py')) or (item.is_dir() and (item / '__init__.py').is_file()):
            try:
                log.debug('Importing %s', mod_name)
                api = BotCoreAPIImpl(
                    config=cfg,
                    register_api_provider=add_api,
                    get_api_provider=get_api,
                    register_web_router=register_web_blueprint,
                )
                module = LoadedModule.load_from(mod_name, api)
            except Exception as err:
                log.critical('Module %s failed to load properly!', mod_name, exc_info=err)
                raise
            else:
                log.debug('Module %s is loaded.', mod_name)
                loaded_modules.append(module)
    # Позволяем модулям инициализироваться
    if not loaded_modules:
        log.info('No available modules found.')
    else:
        LoadedModule.sort_dependencies(loaded_modules)
        log.info('Loaded modules: %s', ','.join([m.name for m in loaded_modules]))
        for module in loaded_modules:
            log.debug('Initializing module %s.', module.name)
            try:
                await module.enter_context()
            except Exception as err:
                log.critical('Module %s failed to initialize!', module.name, exc_info=err)
                raise
        log.info('All modules initialized successfully.')
    # выполняем post-init, если модуль этого требует
    for module in loaded_modules[::-1]:
        try:
            await module.run_post_init()
        except Exception as err:
            log.critical('Module %s failed to run its post-init phase!', module.name, exc_info=err)
            raise

    try:
        yield
    finally:
        log.debug('Shutting down modules...')
        all_ok = True
        for module in loaded_modules[::-1]:
            try:
                await module.exit_context()
            except StopAsyncIteration:
                log.debug('Module %s has been shut down.', module.name)
            except Exception as err:
                all_ok = False
                log.warning('Module %s failed to shutdown properly!', module.name, exc_info=err)
            else:
                all_ok = False
                log.warning('Module %s failed to shutdown properly: there are too many yields!', module.name)
        if all_ok:
            log.info('All modules shut down successfully.')
        else:
            log.warning('Some modules failed to shut down correctly.')
