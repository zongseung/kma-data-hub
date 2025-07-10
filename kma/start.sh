#!/bin/bash

# Docker 이미지 빌드
echo "Docker 이미지 빌드 중..."
docker-compose build

# 컨테이너 시작
echo "컨테이너 시작 중..."
docker-compose up -d

echo "기상 데이터 다운로더가 시작되었습니다!"
echo "웹 브라우저에서 http://localhost:8000 에 접속하세요."

# 로그 확인
docker-compose logs -f
