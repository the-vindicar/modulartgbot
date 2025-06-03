FROM python:3.12-slim-bookworm
LABEL authors="Vindicar"
LABEL description="This service is a multi-part bot assisting with a number of tasks often done by KSU teachers."
WORKDIR /code/multibot

COPY requirements.txt requirements.txt
RUN cat requirements.txt
RUN pip install -r requirements.txt

COPY data /data/multibot
COPY main.py main.py
COPY api api
COPY modules modules

ENV PYTHONUNBUFFERED=TRUE
CMD ["python", "/code/multibot/main.py"]
