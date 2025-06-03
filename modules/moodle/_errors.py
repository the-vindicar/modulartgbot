from typing import Any, Dict, Callable, TypeVar, NoReturn, final

__all__ = ['MoodleError', 'InvalidToken', 'InvalidParameter']
ME = TypeVar('ME', bound='MoodleError')


class MoodleError(RuntimeError):
    __slots__ = ('message', 'exception', 'errorcode', 'data')
    known_errors: Dict[str, ME] = {}

    @classmethod
    @final
    def register(cls, error_code: str) -> Callable[[ME], ME]:
        def wrapper(subclass: ME) -> ME:
            cls.known_errors[error_code] = subclass
            return subclass
        return wrapper

    @classmethod
    @final
    def make_and_raise(cls, response: Dict[str, Any]) -> NoReturn:
        if 'errorcode' in response:
            klass = cls.known_errors.get(response['errorcode'], cls)
            raise klass(response.get('message', ''), response['exception'], response['errorcode'], response)
        else:
            raise MoodleError(response.get('message', ''), response['exception'], '', response)

    def __init__(self, message, exception=None, errorcode=None, data=None):
        super().__init__(message, exception, errorcode, data)
        self.message = message
        self.exception = exception
        self.errorcode = errorcode
        self.data = data

    def __str__(self):
        if self.errorcode:
            return f"[{self.errorcode}] {self.message}"
        else:
            return f"{self.message}"


@MoodleError.register('invalidtoken')
class InvalidToken(MoodleError):
    pass


@MoodleError.register('invalidparameter')
class InvalidParameter(MoodleError):
    pass
