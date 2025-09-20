"""Provides classes corresponding to some typical Moodle errors."""
from typing import Any, Dict, Callable, TypeVar, NoReturn, final

__all__ = ['MoodleError', 'WebServerError', 'InvalidToken', 'InvalidParameter', 'AccessDenied']
ME = TypeVar('ME', bound='MoodleError')


class MoodleError(RuntimeError):
    """Base class for Moodle errors."""
    __slots__ = ('message', 'exception', 'errorcode', 'data')
    known_errors: Dict[str, ME] = {}

    @classmethod
    @final
    def register(cls, error_code: str) -> Callable[[ME], ME]:
        """Allows to associate a descendant class with certain error code, so ``make_and_raise()`` can throw it."""
        def wrapper(subclass: ME) -> ME:
            """Required to implement a parametrized decorator"""
            cls.known_errors[error_code] = subclass
            return subclass
        return wrapper

    @classmethod
    @final
    def make_and_raise(cls, url: str, response: Dict[str, Any]) -> NoReturn:
        """Analyzes a typical Moodle error response and throws a corresponding exception."""
        msg = response.get('message', '') or response.get('error', '')
        klass = cls.known_errors.get(response['errorcode'], cls)
        raise klass(message=msg, url=url,
                    exception=response.get('exception', ''), errorcode=response.get('errorcode', ''),
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


class WebServerError(MoodleError):
    """This error means server returned a 5XX code. This could be a temporary problem."""


@MoodleError.register('invalidtoken')
class InvalidToken(MoodleError):
    """This error means our token has expired, and we need to log in again. That is usually handled automatically."""


@MoodleError.register('invalidparameter')
class InvalidParameter(MoodleError):
    """This error means one of the parameters in the API call was not correct.
    Unfortunately, Moodle never says which, and why."""


@MoodleError.register('accessexception')
class AccessDenied(MoodleError):
    """This error means we do not have a permission/capability to perform this operation."""
