FROM python:3.12-alpine

WORKDIR /app

RUN pip install --no-cache-dir prometheus-client==0.20.0

COPY exporter.py /app/exporter.py

EXPOSE 8080

CMD ["python", "-u", "/app/exporter.py"]
