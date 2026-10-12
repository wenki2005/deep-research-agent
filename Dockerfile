FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY app.py ./app.py
COPY evals ./evals

RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "research_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
