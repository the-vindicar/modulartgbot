from typing import Any, Dict, Callable, TypeVar, NoReturn, final

__all__ = ['MoodleError', 'InvalidToken', 'InvalidParameter', 'AccessDenied']
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
    def make_and_raise(cls, url: str, response: Dict[str, Any]) -> NoReturn:
        if 'errorcode' in response:
            klass = cls.known_errors.get(response['errorcode'], cls)
            raise klass(message=response.get('message', ''), url=url,
                        exception=response['exception'], errorcode=response['errorcode'],
                        data=response)
        else:
            raise MoodleError(message=response.get('message', ''), url=url,
                              exception=response['exception'], errorcode='',
                              data=response)

    def __init__(self, message: str, url: str = None, exception=None, errorcode=None, data=None):
        super().__init__(message, url, exception, errorcode, data)
        self.message = message
        self.url = url
        self.exception = exception
        self.errorcode = errorcode
        self.data = data

    def __str__(self):
        if self.errorcode:
            return f"[{self.errorcode}] {self.message}\nUrl: {self.url}\nData: {self.data!r}"
        else:
            return f"{self.message}\nUrl: {self.url}\nData: {self.data!r}"


@MoodleError.register('invalidtoken')
class InvalidToken(MoodleError):
    pass


@MoodleError.register('invalidparameter')
class InvalidParameter(MoodleError):
    pass


@MoodleError.register('accessexception')
class AccessDenied(MoodleError):
    pass
