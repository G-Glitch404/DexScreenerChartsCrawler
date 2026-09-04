FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:${PATH}" \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER=/usr/bin/chromedriver

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    ca-certificates \
    curl \
    fonts-liberation \
    libnss3 \
    libgtk-3-0 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgbm1 \
    libx11-xcb1 \
    libxtst6 \
    libdrm2 \
    libu2f-udev \
    libvulkan1 \
    libappindicator3-1 \
    xdg-utils \
    tini \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

COPY pyproject.toml uv.lock /app/

RUN uv sync --locked --no-dev

COPY src /app/src

EXPOSE 9098

ENTRYPOINT ["tini", "--"]

CMD ["uv", "run", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "9098"]
