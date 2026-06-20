# 급똥 서울 (Geup-Ddong Seoul) MCP 서버 컨테이너 이미지
#
#   build:  podman build --format docker -t geup-ddong-seoul-mcp .
#           (HEALTHCHECK는 docker 포맷에서만 적용됨. 기본 OCI 포맷이면 무시된다)
#   run:    podman run --rm -p 8000:8000 -v gds-cache:/data geup-ddong-seoul-mcp
#   check:  curl http://localhost:8000/health   ->  {"ok":true,"count":4538,...}
#   MCP:    http://localhost:8000/mcp
#
FROM python:3.12-slim

# 런타임 기본값: 로그 즉시 출력, .pyc 미생성, pip 캐시/버전체크 비활성
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1) 의존성 먼저 설치 (소스보다 앞에 둬 레이어 캐시 활용)
COPY requirements.txt ./
RUN pip install -r requirements.txt

# 2) 애플리케이션 소스 (패키지만 복사)
COPY seoul_toilet/ ./seoul_toilet/

# 3) 컨테이너 기본 환경변수
#    - HOST는 반드시 0.0.0.0: 컨테이너 외부(호스트)에서 접근 가능하게 한다.
#    - CACHE_DIR은 /data(볼륨)로 빼 재시작 간 다운로드 캐시를 유지한다.
#    - 도메인/리버스 프록시 뒤에 둘 경우 SEOUL_TOILET_PUBLIC_HOST=<도메인> 를 추가로 지정.
ENV SEOUL_TOILET_HOST=0.0.0.0 \
    SEOUL_TOILET_PORT=8000 \
    SEOUL_TOILET_CACHE_DIR=/data \
    SEOUL_TOILET_DOWNLOAD_ON_START=1

# 4) 비루트 사용자 + 쓰기 가능한 캐시 디렉터리
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data \
    && chown -R app:app /data /app
USER app

VOLUME ["/data"]
EXPOSE 8000

# 5) 헬스체크: /health 를 파이썬 표준 라이브러리로 점검(slim 이미지에 curl 없음).
#    시작 시 1회 데이터 다운로드가 끝나야 포트가 열리므로 start-period를 넉넉히 둔다.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import os,urllib.request,sys; \
url='http://127.0.0.1:%s/health' % os.environ.get('SEOUL_TOILET_PORT','8000'); \
sys.exit(0 if urllib.request.urlopen(url, timeout=5).status==200 else 1)"

CMD ["python", "-m", "seoul_toilet.server"]
