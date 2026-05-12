FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY inbox_lens ./inbox_lens
COPY config/rules.toml.example ./config/rules.toml.example

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir ".[html]"

RUN useradd --create-home --shell /usr/sbin/nologin inboxlens \
    && mkdir -p /app/data /app/out /app/config \
    && chown -R inboxlens:inboxlens /app

USER inboxlens

EXPOSE 8765

CMD ["inbox-lens", "console", "--host", "0.0.0.0", "--no-browser"]
