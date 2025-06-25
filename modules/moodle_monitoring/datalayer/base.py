from api import DBModel


__all__ = ['MoodleBase']


class MoodleBase(DBModel):
    __abstract__ = True
