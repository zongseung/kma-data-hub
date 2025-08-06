import os
import json
import pandas as pd
import uuid
import threading
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from urllib.parse import unquote
import io

from fastapi import (
    FastAPI, Request, Depends, HTTPException,
    Form, BackgroundTasks, Query
)
from fastapi.responses import (
    HTMLResponse, FileResponse, JSONResponse, StreamingResponse
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

# ASOS.py에서 load_station_map과 get_weather_data를 가져옵니다.
from ASOS import load_station_map, fetch_asos_data

# CSV_PATH 정의 (환경변수 우선)
CSV_PATH = os.getenv("DATA_DIR", "/app/data/asos.csv")
# station_map: 이름->코드, code2name: 코드->이름, codes: 모든 코드
code2name, station_map, codes = load_station_map(CSV_PATH)


# (기존 단기예보용 다운로드 로직과 인증/DB 등은 그대로 유지)
from weather_downloader import WeatherDownloader, DownloadConfig
from databases import (
    RegionDatabase, init_db,
    create_download_log, get_downloads_by_client,
    create_user, get_user_by_username
)
from auth import (
    authenticate_user, create_access_token,
    get_current_user, get_password_hash
)

# ──────────────────────────────────────────────────────────
# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI 앱 선언
app = FastAPI(title="기상 데이터 다운로더")

# 정적 파일 및 템플릿 설정
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# DB 초기화
@app.on_event("startup")
def on_startup():
    init_db()

# 다운로드 작업 상태 저장소
download_tasks: Dict[str, dict] = {}
task_lock = threading.Lock()

# 지역 DB (단기예보용)
DB_PATH = os.getenv("DB_PATH", "data/local_codes.db")
region_db = RegionDatabase(db_path=DB_PATH)

# 클라이언트 ID 미들웨어
class ClientIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = request.cookies.get("client_id")
        if not cid:
            cid = str(uuid.uuid4())
            set_cookie = True
        else:
            set_cookie = False
        request.state.client_id = cid
        response = await call_next(request)
        if set_cookie:
            response.set_cookie(
                "client_id", cid,
                max_age=60*60*24*365,
                path="/", httponly=False
            )
        return response

app.add_middleware(ClientIDMiddleware)

# ──────────────────────────────────────────────────────────
# 홈 페이지
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 단기예보용: 지역 조회
@app.get("/api/regions", response_class=JSONResponse)
async def get_regions(search: Optional[str] = Query("", description="검색어")):
    try:
        regions = region_db.get_available_regions(search_term=search)
        return {"regions": regions}
    except Exception as e:
        logger.error(f"지역 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="지역 조회 중 오류 발생")

@app.get("/api/configs")
async def get_configs():
    configs = [
        {
            "name": "단기예보",
            "description": "3일간의 기상예보 (3시간 간격)",
            "variables": [
                {"code": "TMP", "name": "1시간기온"},
                {"code": "WSD", "name": "풍속"},
                {"code": "SKY", "name": "하늘상태"},
                {"code": "REH", "name": "습도"},
                {"code": "TMX", "name": "일최고기온"},
                {"code": "TMN", "name": "일최저기온"},
                {"code": "PTY", "name": "강수형태"},
                {"code": "POP", "name": "강수확률"},
                {"code": "UUU", "name": "동서바람성분"},
                {"code": "VVV", "name": "남북바람성분"},
                {"code": "PCP", "name": "1시간강수량"},
                {"code": "SNO", "name": "1시간적설"},
                {"code": "WAV", "name": "파고"},
                {"code": "VEC", "name": "풍향"}
            ]
        },
        {
            "name": "초단기실황",
            "description": "현재 기상 실황 (1시간 간격)",
            "variables": [
                {"code": "PTY", "name": "강수형태"},
                {"code": "REH", "name": "습도"},
                {"code": "RN1", "name": "강수"},
                {"code": "SKY", "name": "하늘상태"},
                {"code": "T1H", "name": "기온"},
                {"code": "LGT", "name": "뇌전"},
                {"code": "VEC", "name": "풍향"},
                {"code": "WSD", "name": "풍속"}
            ]
        },
        {
            "name": "초단기예보",
            "description": "6시간 기상예보 (1시간 간격)",
            "variables": [
                {"code": "PTY", "name": "강수형태"},
                {"code": "REH", "name": "습도"},
                {"code": "RN1", "name": "강수"},
                {"code": "SKY", "name": "하늘상태"},
                {"code": "T1H", "name": "기온"},
                {"code": "LGT", "name": "뇌전"},
                {"code": "VEC", "name": "풍향"},
                {"code": "WSD", "name": "풍속"},
                {"code": "UUU", "name": "동서바람성분"},
                {"code": "VVV", "name": "남북바람성분"}
            ]
        }
    ]
    return {"configs": configs}


# 인증 토큰 발급
@app.post("/api/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token({"sub": user['username']})
    return {"access_token": token, "token_type": "bearer"}

# 단기예보 다운로드 시작
@app.post("/api/download", response_class=JSONResponse)
async def start_download(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    login_id: str = Form(...),
    password: str = Form(...),
    regions: str = Form(...),
    config_name: str = Form(...),
    variables: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
):
    try:
        region_objs = json.loads(regions)
        var_objs    = json.loads(variables)
        cfg = DownloadConfig(
            login_id=login_id,
            password=password,
            regions=region_objs,
            config_name=config_name,
            variables=var_objs,
            start_date=datetime.strptime(start_date, "%Y-%m-%d"),
            end_date=  datetime.strptime(end_date, "%Y-%m-%d"),
        )
        tid = str(uuid.uuid4())
        with task_lock:
            download_tasks[tid] = {
                "status":"started","progress":0,"total":0,
                "current_item":"","error":None,
                "files":[],"start_time":datetime.now(),
            }
        background_tasks.add_task(
            run_download, tid, cfg,
            client_id=request.state.client_id,
            username=current_user['username']
        )
        return {"task_id":tid,"status":"started"}
    except Exception as e:
        logger.error(f"다운로드 시작 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 다운로드 상태 조회
@app.get("/api/status/{task_id}", response_class=JSONResponse)
async def get_download_status(task_id: str):
    with task_lock:
        if task_id not in download_tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        data = download_tasks[task_id].copy()
    elapsed = datetime.now() - data["start_time"]
    data["elapsed_time"] = str(elapsed).split(".")[0]
    return data

# 다운로드된 파일 목록 & 개별 다운로드
@app.get("/api/files", response_class=JSONResponse)
async def get_downloaded_files():
    dl_dir = "downloads"
    out = []
    if os.path.exists(dl_dir):
        for r, _, fns in os.walk(dl_dir):
            for fn in fns:
                if fn.endswith(".csv"):
                    full = os.path.join(r, fn)
                    st = os.stat(full)
                    out.append({
                        "name":fn, "path":os.path.relpath(full, dl_dir),
                        "size":st.st_size,
                        "modified":datetime.fromtimestamp(st.st_mtime).isoformat()
                    })
    return {"files": sorted(out, key=lambda x: x["modified"], reverse=True)}

@app.get("/api/download-file/{file_path:path}")
async def download_file(file_path: str):
    real = unquote(file_path)
    full = os.path.join("downloads", real)
    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full, media_type="application/octet-stream", filename=os.path.basename(full))

# 백그라운드 작업
async def run_download(task_id: str, cfg: DownloadConfig, client_id: str, username: str):
    try:
        dw = WeatherDownloader()
        def p_cb(cur, tot, item):
            with task_lock:
                download_tasks[task_id].update({
                    "status":"downloading",
                    "progress":cur,"total":tot,"current_item":item
                })
        def f_cb(path):
            with task_lock:
                download_tasks[task_id]["files"].append(path)
        await dw.download(cfg, p_cb, f_cb, client_id)
        with task_lock:
            download_tasks[task_id].update({
                "status":"completed",
                "progress":download_tasks[task_id]["total"],
                "current_item":"완료"
            })
        user = get_user_by_username(username)
        for p in download_tasks[task_id]["files"]:
            create_download_log(client_id, os.path.basename(p), "success")
    except Exception as e:
        logger.error(f"다운로드 오류 ({task_id}): {e}")
        with task_lock:
            download_tasks[task_id].update({
                "status":"error","error":str(e)
            })

# ASOS 관측소 목록
@app.get("/api/asos/stations", response_class=JSONResponse)
def api_asos_stations():
    # return {"stations": [{"name": n, "code": c} for n, c in station_map.items()]}
    return {"stations": [{"name": name, "code": code} for name, code in station_map.items()]}

#$####$####$####$####$####$###
SERVICE_KEY = "iCNxo2r0TdZnnV63/ItO+QrOUqJakXCxx/m20BsCp53DGZzJMDd1/7jOGLYQE+Sn+1EQeSeIhUsTIyQ5dYgy4Q=="


# ASOS 다운로드
@app.get("/api/download/asos", response_class=StreamingResponse)
def api_download_asos(
    start_date:  str = Query(..., alias="start", description="시작 날짜 (YYYYMMDD)"),
    end_date:    str = Query(..., alias="end",   description="종료 날짜 (YYYYMMDD)"),
    region_key:  str = Query(..., alias="stnIds",description="지역 이름 또는 관측소 코드"),
    service_key: str = Query(None, alias="service_key", description="기상청 API 키 (선택)"),
):
    logger.info(f"ASOS download request - start={start_date}, end={end_date}, key={region_key}")

    # 1) 날짜 검증
    for d in (start_date, end_date):
        try:
            datetime.strptime(d, "%Y%m%d")
        except ValueError:
            raise HTTPException(400, detail="start/end 파라미터가 YYYYMMDD 형식이 아닙니다.")

    # 2) 서비스 키
    key = service_key or os.getenv("SERVICE_KEY") or ""
    if not key:
        raise HTTPException(500, detail="SERVICE_KEY가 설정되지 않았습니다.")

    # 3) 데이터 조회
    try:
        df = fetch_asos_data(key, start_date, end_date, region_key)
    except ValueError as e:
        logger.error(f"Invalid parameter: {e}")
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        raise HTTPException(502, detail=f"외부 API 호출 실패: {e}")

    if df.empty:
        raise HTTPException(404, detail="해당 조건의 데이터가 없습니다.")

    # 4) CSV 스트림
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    filename = f"ASOS_{region_key}_{start_date}_{end_date}.csv"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(buf, media_type="text/csv", headers=headers)# 애플리케이션 실행

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)