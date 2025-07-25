import enum

from pydantic import BaseModel, Field

from modules.settings.forms import model2fields


def test_simplemodel():
    class Color(enum.StrEnum):
        RED = 'red'
        GREEN = 'green'
        BLUE = 'blue'

    class Point(BaseModel):
        x: int
        y: int

    class Line(BaseModel):
        """Прямая линия"""
        start: Point = Field(description="Начало")
        end: Point = Field(description="Конец")
        color: Color = Field(description="Цвет")

    print(model2fields(Line(start=Point(x=0, y=0), end=Point(x=1, y=1), color=Color.BLUE)))


if __name__ == '__main__':
    test_simplemodel()
