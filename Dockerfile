FROM python:3.11-slim

WORKDIR /app

COPY requirements_docker.txt .

RUN pip install --no-cache-dir -r requirements_docker.txt

COPY . .

ENV CUDA_VISIBLE_DEVICES=""

CMD ["python", "src/test_retrieval2.py"]