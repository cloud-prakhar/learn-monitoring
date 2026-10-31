# Dockerfile for the psutil System Monitor (Project 6)
#
# psutil ships pre-built manylinux wheels, so python:3.12-slim needs no compiler.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 -r requirements.txt

COPY app.py .

# psutil reads the host's /proc (mounted by docker-compose.yml).
ENV PROCFS_PATH=/host/proc

EXPOSE 8086

CMD ["python", "app.py"]
