FROM python:3.11-slim

WORKDIR /app

# Cài đặt dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Thiết lập biến môi trường
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "tests/test_pipeline.py"]