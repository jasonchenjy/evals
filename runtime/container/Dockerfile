FROM python:3.8.20-slim-bookworm@sha256:1d52838af602b4b5a831beb13a0e4d073280665ea7be7f69ce2382f29c5a613f
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/eval-requirements.txt
RUN python -m venv /opt/pytest-python && /opt/pytest-python/bin/python -m pip install --no-deps -r /tmp/eval-requirements.txt
RUN mkdir -p /trial && chmod 700 /trial && chown 1000:1000 /trial
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
