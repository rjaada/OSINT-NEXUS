FROM python:3.11-slim

WORKDIR /app

# build-essential (gcc + libc headers) is needed for the `mgrs` package's
# C extension — it only ships prebuilt wheels for x86_64 on PyPI, so arm64
# (Apple Silicon) hosts fall back to a source build.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
