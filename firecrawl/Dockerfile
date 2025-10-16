FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

# System deps for pdf/text parsing + timezones
RUN apt-get update && apt-get install -y --no-install-recommends     gcc libc6-dev libxml2 libxslt1.1 libxslt1-dev curl tzdata     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY ./utils /app/utils
COPY ./main.py /app/main.py
COPY ./config.yaml /app/config.yaml

RUN pip install --no-cache-dir     requests==2.32.3     beautifulsoup4==4.12.3     pyyaml==6.0.2     pdfminer.six==20240706     python-docx==1.1.2     unstructured==0.15.13     lxml==5.2.1

ENTRYPOINT ["python", "/app/main.py"]
