FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt


# 그 다음에 남은 애플리케이션 코드 복사
COPY main.py databases.py weather_downloader.py ./
COPY static ./static
COPY templates ./templates

RUN mkdir -p downloads

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]