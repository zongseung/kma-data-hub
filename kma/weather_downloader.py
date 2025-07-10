import os
import zipfile
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import asyncio
import time
from dataclasses import dataclass
from typing import List, Dict, Callable, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class DownloadConfig:
    login_id: str
    password: str
    regions: List[Dict]
    config_name: str
    variables: List[Dict]
    start_date: datetime
    end_date: datetime

class WeatherDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.configs = {
            "단기예보": {
                "code": "424",
                "api": "request420",
                "mode": "range",
                "reqst_purpose_cd": "F00415",
                "request_url": "https://data.kma.go.kr/mypage/rmt/callDtaReqstIrods4xxNewAjax.do",
                "selectType": "1",
            },
            "초단기실황": {
                "code": "400",
                "api": "request400",
                "mode": "monthly",
                "reqst_purpose_cd": "F00401",
                "request_url": "https://data.kma.go.kr/mypage/rmt/callDtaReqstIrods4xxAjax.do",
                "selectType": "1",
            },
            "초단기예보": {
                "code": "411",
                "api": "request410",
                "mode": "range",
                "reqst_purpose_cd": "F00415",
                "request_url": "https://data.kma.go.kr/mypage/rmt/callDtaReqstIrods4xxNewAjax.do",
                "selectType": "1",
            }
        }
    
    def get_cookie(self, login_id: str, password: str) -> str:
        logger.info("기상청 로그인 중...")
        url = "https://data.kma.go.kr/login/loginAjax.do"
        resp = self.session.post(url, data={"loginId": login_id, "passwordNo": password})
        resp.raise_for_status()
        time.sleep(2)
        return "; ".join(f"{k}={v}" for k,v in self.session.cookies.get_dict().items())
    
    def make_headers(self, cookie: str):
        """요청 헤더 생성"""
        first = {
            "Accept": "text/plain, */*; q=0.01",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Cookie": cookie,
            "Host": "data.kma.go.kr",
            "Origin": "https://data.kma.go.kr",
            "Referer": "https://data.kma.go.kr/data/rmt/rmtList.do",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        
        second = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": cookie,
            "Host": "data.kma.go.kr",
            "Origin": "https://data.kma.go.kr",
            "Referer": "https://data.kma.go.kr/data/rmt/rmtList.do",
            "Sec-Fetch-Dest": "iframe",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        
        return first, second
    
    def generate_intervals(self, start: datetime, end: datetime, mode: str):
        """날짜 구간 생성"""
        intervals = []
        if mode == "monthly":
            current = start.replace(day=1)
            while current <= end:
                intervals.append((current.strftime("%Y%m"), current.strftime("%Y%m")))
                current += relativedelta(months=1)
        else:  # range mode
            current = start
            while current < end:
                next_date = current + relativedelta(months=1)
                if next_date > end:
                    next_date = end
                intervals.append((current.strftime("%Y%m%d"), next_date.strftime("%Y%m%d")))
                current = next_date
        return intervals
    
    def generate_request_body(self,
                              var_name: str,
                              var_code: str,
                              start: str,
                              end: str,
                              station: str,
                              region_code: str,                 
                              config: Dict) -> Dict:
         
        return {
            "apiCd": config["api"],
            "data_code": config["code"],
            "hour": "",
            "pageIndex": "1",
            "from": start,
            "to": end,
            "reqst_purpose_cd": config["reqst_purpose_cd"],
            "recordCountPerPage": "10",
            "txtVar1Nm": var_name,
            "selectType": config["selectType"],
            "startDt": start[:4],
            "startMt": start[4:6],
            "endDt": end[:4],
            "endMt": end[4:6],
            "from_": start,
            "to_": end,
            "var1": var_code,
            "var3": region_code,
            "stnm": station,
            "elcd": var_name,
            "strtm": start,
            "endtm": end,
            "req_list": f"{start}|{end}|{config['code']}|{var_code}|{region_code}",
        }
    
    async def download(
        self,
        config: DownloadConfig,
        progress_callback: Callable[[int,int,str], None],
        file_callback: Callable[[str], None]
    ):
        try:
            # 1) 로그인 & 헤더 준비
            cookie = self.get_cookie(config.login_id, config.password)
            hdr1, hdr2 = self.make_headers(cookie)

            # 2) 설정 & 날짜구간
            cfg = self.configs[config.config_name]
            intervals = self.generate_intervals(config.start_date, config.end_date, cfg["mode"])

            total = len(config.regions) * len(intervals) * len(config.variables)
            cur_idx = 0

            # 3) 다운로드 디렉토리
            base_dir = os.path.join("downloads", config.config_name)
            os.makedirs(base_dir, exist_ok=True)

            # 4) 실제 다운로드 루프
            for region in config.regions:
                region_dir = os.path.join(base_dir, region["level1"], region["level2"], region["level3"])
                os.makedirs(region_dir, exist_ok=True)

                for start, end in intervals:
                    for variable in config.variables:
                        cur_idx += 1
                        name, code = variable["name"], variable["code"]

                        # 진행 콜백
                        progress_callback(cur_idx, total, f"{region['level3']} - {name} ({start}~{end})")

                        # 5) 요청 바디 생성 (nx, ny 포함)
                        req_body = self.generate_request_body(
                        variable["name"],   # var_name
                        variable["code"],   # var_code
                        start,              # start
                        end,                # end
                        region["level3"],   # station
                        region["code"],     # region_code
                        cfg                  # config dict
                    )

                        # 6) 데이터 요청
                        self.session.post(cfg["request_url"], headers=hdr1, data=req_body)

                        # 7) ZIP 다운로드 & 압축 해제 로직 (기존 그대로)
                        download_payload = {"downFile": f"{region['level3']}_{name}_{start}_{end}.csv"}
                        resp = self.session.post(
                            "https://data.kma.go.kr/data/rmt/downloadZip.do",
                            headers=hdr2, data=download_payload, stream=True
                        )

                        if resp.status_code == 200:
                            zip_path = os.path.join(region_dir, f"{region['level3']}_{name}_{start}_{end}.zip")
                            with open(zip_path, "wb") as f:
                                for chunk in resp.iter_content(8192):
                                    f.write(chunk)

                            var_dir = os.path.join(region_dir, name)
                            os.makedirs(var_dir, exist_ok=True)

                            with zipfile.ZipFile(zip_path) as z:
                                for info in z.infolist():
                                    try:
                                        fn = info.filename.encode("cp437").decode("euc-kr")
                                    except:
                                        fn = info.filename
                                    tgt = os.path.join(var_dir, fn)
                                    with open(tgt, "wb") as out:
                                        out.write(z.read(info.filename))
                                    file_callback(tgt)

                            os.remove(zip_path)

                        # API 과부하 방지를 위한 짧은 대기
                        await asyncio.sleep(0.5)

            logger.info("모든 다운로드 완료")

        except Exception as e:
            logger.error(f"다운로드 중 오류 발생: {e}")
            raise