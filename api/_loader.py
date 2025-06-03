import contextlib
import dataclasses
import importlib
import sys
from pathlib import Path
import logging
from typing import cast, final, Optional, Container, Coroutine, AsyncGenerator, Callable, Type, ClassVar, TypeVar

import quart

from ._protocols import CoreAPI, PluginAPI, ConfigManager


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
    MODULES_DIR: ClassVar[str] = 'modules'
    name: str
    requires: frozenset[Type]
    provides: frozenset[Type]
    lifetime: Callable[[CoreAPI], AsyncGenerator]
    api: BotCoreAPIImpl
    context: Optional[AsyncGenerator]

    @staticmethod
    def load_from(mod_name: str, api: BotCoreAPIImpl) -> 'LoadedModule':
        module: PluginAPI = cast(PluginAPI, importlib.import_module(f'{LoadedModule.MODULES_DIR}.{mod_name}'))
        requires = frozenset(getattr(module, 'requires', None) or tuple())
        provides = frozenset(getattr(module, 'provides', None) or tuple())
        return LoadedModule(
            name=mod_name,
            requires=requires,
            provides=provides,
            lifetime=module.lifetime,
            api=api,
            context=None
        )

    @staticmethod
    def sort_dependencies(loaded: list['LoadedModule']) -> None:
        available: set[Type] = set()
        ordered: list['LoadedModule'] = []
        unordered = loaded.copy()
        while unordered:
            added_any = False
            for i in range(len(unordered)-1, -1, -1):
                if available.issuperset(unordered[i].requires):
                    ordered.append(unordered[i])
                    available.update(unordered[i].provides)
                    del unordered[i]
                    added_any = True
            if not added_any:
                unmet = []
                for m in unordered:
                    missing = ', '.join(t.__qualname__ for t in (set(m.requires) - available))
                    unmet.append(f'{m.name} ({missing})')
                raise ValueError(f'Modules with unmet dependencies: {"; ".join(unmet)}')
        loaded[:] = ordered

    async def enter_context(self) -> None:
        if self.context is None:
            self.context = self.lifetime(self.api)
            await self.context.__anext__()

    async def exit_context(self) -> None:
        if self.context is not None:
            self.context, ctx = None, self.context
            await ctx.__anext__()


@contextlib.asynccontextmanager
async def modules_lifespan(
        webapp: quart.Quart,
        cfg: ConfigManager,
        *, module_whitelist: Container[str] = None
        ):
    log = logging.getLogger('modules')
    module_api_providers: dict[type, Coroutine] = {}

    def get_api(api_provider):
        return module_api_providers[api_provider]

    def add_api(api_provider: Coroutine, api_class: type) -> None:
        if api_class in module_api_providers:
            raise KeyError(f'API {api_class.__name__} has already been provided.')
        module_api_providers[api_class] = api_provider

    def register_web_blueprint(blueprint):
        webapp.register_blueprint(blueprint)

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
