# Dockerfile for the System Monitor (Project 4)
#
# python:3.12-slim keeps the image small. The app only needs Flask and
# prometheus-client — it reads /proc with plain open() calls, no extra libraries.

FROM python:3.12-slim

WORKDIR /app

# Copy requirements first so Docker can cache the pip install layer.
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 -r requirements.txt

COPY app.py .

# Read the host's /proc (mounted by docker-compose.yml), not the container's own.
ENV PROC_ROOT=/host/proc

EXPOSE 8084

CMD ["python", "app.py"]
