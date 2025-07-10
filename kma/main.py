from fastapi import FastAPI, Request, Form, HTTPException, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional, Dict
from datetime import datetime
import os, json, uuid, threading, logging
from fastapi.responses import FileResponse
import urllib.parse
from urllib.parse import quote

from weather_downloader import WeatherDownloader, DownloadConfig
from databases import RegionDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="기상 데이터 다운로더")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

download_tasks: Dict[str, dict] = {}
task_lock = threading.Lock()

DB_PATH = os.getenv("DB_PATH", "data/local_codes.db")
region_db = RegionDatabase(db_path=DB_PATH)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/regions", response_class=JSONResponse)
async def get_regions(search: Optional[str] = Query("", description="검색어")):
    try:
        regions = region_db.get_available_regions(search_term=search)
        return {"regions": regions}
    except Exception as e:
        logger.error(f"지역 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="지역 조회 중 오류 발생")

@app.get("/api/configs", response_class=JSONResponse)
async def get_configs():
    return {
        "configs": [
            {
                "name": "단기예보",
                "description": "3일간 기상예보 (3시간 간격)",
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
                    {"code": "VEC", "name": "풍향"},
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
                    {"code": "WSD", "name": "풍속"},
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
                    {"code": "VVV", "name": "남북바람성분"},
                ]
            }
        ]
    }

@app.post("/api/download", response_class=JSONResponse)
async def start_download(
    background_tasks: BackgroundTasks,
    login_id: str = Form(...),
    password: str = Form(...),
    regions: str = Form(...),
    config_name: str = Form(...),
    variables: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...)
):
    try:
        # JSON 포맷 그대로 딕셔너리 리스트로 파싱
        region_objs = json.loads(regions)     # List[{"level1":...,"level2":...,"level3":...,"code":...},…]
        var_objs    = json.loads(variables)   # List[{"code":…,"name":…},…]

        config = DownloadConfig(
            login_id=login_id,
            password=password,
            regions=region_objs,          # ← **여기** 반드시 dict 리스트
            config_name=config_name,
            variables=var_objs,           # ← **여기** 반드시 dict 리스트
            start_date=datetime.strptime(start_date, "%Y-%m-%d"),
            end_date=datetime.strptime(end_date, "%Y-%m-%d")
        )

        task_id = str(uuid.uuid4())
        with task_lock:
            download_tasks[task_id] = {
                "status": "started",
                "progress": 0,
                "total": 0,
                "current_item": "",
                "error": None,
                "files": [],
                "start_time": datetime.now()
            }

        background_tasks.add_task(run_download, task_id, config)
        return {"task_id": task_id, "status": "started"}

    except Exception as e:
        logger.error(f"다운로드 시작 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status/{task_id}", response_class=JSONResponse)
async def get_download_status(task_id: str):
    with task_lock:
        if task_id not in download_tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        task = download_tasks[task_id].copy()
    elapsed = datetime.now() - task["start_time"]
    task["elapsed_time"] = str(elapsed).split(".")[0]
    return task

@app.get("/api/files", response_class=JSONResponse)
async def get_downloaded_files():
    downloads_dir = "downloads"
    files_list = []
    if os.path.exists(downloads_dir):
        for root, _, fns in os.walk(downloads_dir):
            for fn in fns:
                if fn.endswith(".csv"):
                    full = os.path.join(root, fn)
                    st = os.stat(full)
                    files_list.append({
                        "name": fn,
                        "path": os.path.relpath(full, downloads_dir),
                        "size": st.st_size,
                        "modified": datetime.fromtimestamp(st.st_mtime).isoformat()
                    })
    return {"files": sorted(files_list, key=lambda x: x["modified"], reverse=True)}

@app.get("/api/download-file/{file_path:path}")
async def download_file(file_path: str):
    full_path = os.path.join("downloads", file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    filename = os.path.basename(full_path)
    headers = {
        # 모든 브라우저에서 한글 파일명까지 안전
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
    }
    return FileResponse(
        full_path,
        media_type="text/csv",   # 실제 타입 지정
        headers=headers
    )

async def run_download(task_id: str, config: DownloadConfig):
    try:
        dw = WeatherDownloader()

        def progress_cb(cur, tot, item):
            with task_lock:
                if task_id in download_tasks:
                    download_tasks[task_id].update({
                        "status": "downloading",
                        "progress": cur,
                        "total": tot,
                        "current_item": item
                    })

        def file_cb(path):
            with task_lock:
                if task_id in download_tasks:
                    download_tasks[task_id]["files"].append(path)

        await dw.download(config, progress_cb, file_cb)

        with task_lock:
            download_tasks[task_id].update({
                "status": "completed",
                "progress": download_tasks[task_id]["total"],
                "current_item": "완료"
            })

    except Exception as e:
        logger.error(f"다운로드 오류 ({task_id}): {e}")
        with task_lock:
            download_tasks[task_id].update({
                "status": "error",
                "error": str(e)
            })
            
@app.get("/api/download-file/{file_path:path}")
async def download_file(file_path: str):
    full_path = os.path.join("downloads", file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    # 한글 파일명을 브라우저가 깨지지 않도록 RFC 5987 형식으로 인코딩
    filename = os.path.basename(full_path)
    encoded  = urllib.parse.quote(filename.encode('utf-8'))

    return FileResponse(
        full_path,
        media_type="text/csv",
        filename=filename,                 # FastAPI 0.110+ 이면 이것만으로도 OK
        headers={
            "Content-Disposition":
            f"attachment; filename*=UTF-8''{encoded}"
        }
    )
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
