# Dockerfile for the URL Health Checker (Project 5)

FROM python:3.12-slim

WORKDIR /app

# Copy requirements first so Docker can cache the pip install layer.
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 -r requirements.txt

COPY app.py .

EXPOSE 8085

CMD ["python", "app.py"]
