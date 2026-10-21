FROM docker.io/library/python:3.13-slim-trixie AS base
RUN apt-get update \
    && apt-get install -y --no-install-recommends libimage-exiftool-perl tzdata \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

FROM base AS test
RUN pip install --no-cache-dir ".[dev]"
COPY tests ./tests
CMD ["pytest", "-q"]

FROM base AS app
RUN pip install --no-cache-dir .
ENTRYPOINT ["photo-sorter"]
