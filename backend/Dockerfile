FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install base system dependencies required by the app.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency metadata first so Python dependency installation can be cached.
COPY pyproject.toml ./

# Install Python dependencies from pyproject metadata without tying the layer to app source.
RUN python - <<'PY' > /tmp/requirements.txt
from pathlib import Path
import tomllib

pyproject = tomllib.loads(Path("pyproject.toml").read_text())
for dependency in pyproject["project"]["dependencies"]:
    print(dependency)
PY
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# Install Chromium and Playwright OS dependencies in a stable cache layer.
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Copy runtime source code last so code-only changes do not invalidate dependency layers.
COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
