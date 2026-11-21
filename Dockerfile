FROM python:3.11-slim

ARG INSTALL_TRANSFORMERS=0
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    UV_PYTHON_DOWNLOADS=never

RUN pip install --no-cache-dir uv==0.11.8
COPY pyproject.toml uv.lock ./
RUN if [ "$INSTALL_TRANSFORMERS" = "1" ]; then \
      uv sync --locked --no-dev --extra transformers; \
    else \
      uv sync --locked --no-dev; \
    fi
COPY mail_search ./mail_search
COPY models ./models

CMD ["python", "-m", "mail_search", "serve", "--host", "0.0.0.0"]
