FROM python:3.10.7-slim-buster AS base

ENV PYROOT /pyroot
ENV PYTHONUSERBASE $PYROOT
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN groupadd account_manager
RUN useradd -g account_manager account_manager
RUN chown -R account_manager:account_manager /app

FROM base AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y git gcc python3-dev musl-dev libpq-dev cmake build-essential

COPY Pipfile .
COPY Pipfile.lock .
RUN pip install --upgrade pip
RUN pip install --upgrade setuptools
RUN pip install pipenv
RUN PIP_USER=1 PIP_IGNORE_INSTALLED=1 pipenv install --system --deploy --ignore-pipfile

FROM base
COPY --from=builder $PYROOT/lib/ $PYROOT/lib/