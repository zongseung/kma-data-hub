FROM python:3.11-slim

WORKDIR /app

# Dependencies 설치
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 소스 복사
COPY main.py databases.py ASOS.py weather_downloader.py auth.py ./
COPY static ./static
COPY templates ./templates

# 로그 DB 위치에 따라 디렉터리 생성
RUN mkdir -p downloads data

# 환경변수를 통해 DB 경로와 JWT 시크릿 설정
ENV DB_PATH=/app/data/local_codes.db
ENV SECRET_KEY=YOUR_RANDOM_SECRET_KEY

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]