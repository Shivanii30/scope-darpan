FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ghostscript libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/requirements.txt

COPY darpan /app/darpan
RUN mkdir -p /app/Ombudsman \
    /app/darpan/m0/outputs /app/darpan/m1/outputs /app/darpan/m2/outputs \
    /app/darpan/m3/outputs /app/darpan/m4/outputs /app/darpan/m5/outputs \
    /app/darpan/m6/outputs /app/darpan/m7/outputs /app/darpan/m10/outputs \
    /app/darpan/m10/state \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /app

USER app

EXPOSE 8000 8501

CMD ["uvicorn", "darpan.m8.app:app", "--host", "0.0.0.0", "--port", "8000"]
