FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p outputs

ENV PYTHONPATH=/app/src

CMD ["python", "src/main.py"]
