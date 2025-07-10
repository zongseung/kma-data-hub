import os
import zipfile
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd

# -------------------------------
# 공통: 세션 및 파일 로드
# -------------------------------
session = requests.Session()
BASE_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGION_CODE_PATH = os.path.join(BASE_SCRIPT_DIR, "지역코드_sep.csv")


# -------------------------------
# 공통: 지역 코드 로드 및 슬라이스
# -------------------------------
def load_region_code(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["지역키"] = df["Level1"] + "|" + df["Level2"] + "|" + df["Level3"]
    return df


# -------------------------------
# 공통: 로그인 및 헤더 생성
# -------------------------------
def get_cookie(login_id: str, password: str) -> str:
    print("로그인 중...")
    url = "https://data.kma.go.kr/login/loginAjax.do"
    resp = session.post(url, data={"loginId": login_id, "passwordNo": password})
    resp.raise_for_status()
    cookies = session.cookies.get_dict()
    time.sleep(3)  # 로그인 후 잠시 대기
    return "; ".join([f"{k}={v}" for k, v in cookies.items()])


# 첫 번째, 두 번째 헤더 템플릿
HEADER_TEMPLATE = {
    "first": {
        "Accept": "text/plain, */*; q=0.01",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Host": "data.kma.go.kr",
        "Origin": "https://data.kma.go.kr",
        "Referer": "https://data.kma.go.kr/data/rmt/rmtList.do",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
    },
    "second": {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": "data.kma.go.kr",
        "Origin": "https://data.kma.go.kr",
        "Referer": "https://data.kma.go.kr/data/rmt/rmtList.do",
        "Sec-Fetch-Dest": "iframe",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0",
    },
}


def make_headers(cookie: str):
    first = HEADER_TEMPLATE["first"].copy()
    second = HEADER_TEMPLATE["second"].copy()
    first["Cookie"], second["Cookie"] = cookie, cookie
    return first, second


# -------------------------------
# 공통: 날짜 구간 생성
# -------------------------------
def gen_intervals(
    start: datetime, end: datetime, mode: str = "monthly", delta_months: int = 1
):
    out = []
    if mode == "monthly":
        curr = start.replace(day=1)
        while curr <= end:
            out.append((curr.strftime("%Y%m"), curr.strftime("%Y%m")))
            curr += relativedelta(months=1)
    else:
        curr = start
        while curr < end:
            nxt = curr + relativedelta(months=delta_months)
            if nxt > end:
                nxt = end
            out.append((curr.strftime("%Y%m%d"), nxt.strftime("%Y%m%d")))
            curr = nxt
    return out


# -------------------------------
# 공통: 요청 생성
# -------------------------------
def gen_request_body_common(
    var_name: str,
    var_code: str,
    start: str,
    end: str,
    station: str,
    region_code: str,
    api_cd: str,
    data_cd: str,
    reqst_purpose_cd: str,
    select_type: str,
):
    return {
        "apiCd": api_cd,
        "data_code": data_cd,
        "hour": "",
        "pageIndex": "1",
        "from": start,
        "to": end,
        "reqst_purpose_cd": reqst_purpose_cd,
        "recordCountPerPage": "10",
        "txtVar1Nm": var_name,
        "selectType": select_type,
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
        "req_list": f"{start}|{end}|{data_cd}|{var_code}|{region_code}",
    }


def gen_download_payload(station: str, var_name: str, start: str, end: str):
    return {"downFile": f"{station}_{var_name}_{start}_{end}.csv"}


# -------------------------------
# 설정: 예보 유형별 매핑
# -------------------------------
CONFIGS = [
    {
        "name": "단기예보",
        "code": "424",
        "api": "request420",
        "mode": "range",
        "reqst_purpose_cd": "F00415",
        "interval": (datetime(2021, 10, 1), datetime(2025, 4, 30)),
        "request_url": "https://data.kma.go.kr/mypage/rmt/callDtaReqstIrods4xxNewAjax.do",
        "selectType": "1",
        "vars": [
            ("1시간기온", "TMP"),
            ("풍속", "WSD"),
            ("하늘상태", "SKY"),
            ("습도", "REH"),
            ("일최고기온", "TMX"),
            ("일최저기온", "TMN"),
            ("강수형태", "PTY"),
            ("강수확률", "POP"),
            ("동서바람성분", "UUU"),
            ("남북바람성분", "VVV"),
            ("1시간강수량", "PCP"),
            ("1시간적설", "SNO"),
            ("파고", "WAV"),
            ("풍향", "VEC"),
        ],
    },
    {
        "name": "초단기실황",
        "code": "400",
        "api": "request400",
        "mode": "monthly",
        "reqst_purpose_cd": "F00401",
        "request_url": "https://data.kma.go.kr/mypage/rmt/callDtaReqstIrods4xxAjax.do",
        "interval": (datetime(2010, 7, 1), datetime(2025, 4, 30)),
        "selectType": "1",
        "vars": [
            ("강수형태", "PTY"),
            ("습도", "REH"),
            ("강수", "RN1"),
            ("하늘상태", "SKY"),
            ("기온", "T1H"),
            ("뇌전", "LGT"),
            ("풍향", "VEC"),
            ("풍속", "WSD"),
        ],
    },
    {
        "name": "초단기예보",
        "code": "411",
        "api": "request410",
        "mode": "range",
        "reqst_purpose_cd": "F00415",
        "request_url": "https://data.kma.go.kr/mypage/rmt/callDtaReqstIrods4xxNewAjax.do",
        "interval": (datetime(2021, 7, 1), datetime(2025, 4, 30)),
        "selectType": "1",
        "vars": [
            ("강수형태", "PTY"),
            ("습도", "REH"),
            ("강수", "RN1"),
            ("하늘상태", "SKY"),
            ("기온", "T1H"),
            ("뇌전", "LGT"),
            ("풍향", "VEC"),
            ("풍속", "WSD"),
            ("동서바람성분", "UUU"),
            ("남북바람성분", "VVV"),
        ],
    },
    {
        "name": "구_단기예보",
        "code": "420",
        "api": "request420",
        "mode": "monthly",
        "reqst_purpose_cd": "F00415",
        "interval": (datetime(2008, 10, 1), datetime(2021, 6, 29)),
        "request_url": "https://data.kma.go.kr/mypage/rmt/callDtaReqstIrods4xxAjax.do",
        "selectType": "2",
        "vars": [
            ("3시간기온", "T3H"),
            ("일최고기온", "TMX"),
            ("일최저기온", "TMN"),
            ("하늘상태", "SKY"),
            ("강수형태", "PTY"),
            ("강수확률", "POP"),
            ("6시간강수량", "R06"),
            ("12시간강수량", "R12"),
            ("6시간적설", "S06"),
            ("12시간신적설", "S12"),
            ("습도", "REH"),
            ("파고", "WAV"),
            ("풍속", "WSD"),
            ("풍향", "VEC"),
        ],
    },
    # 자료제공기간은 2010.6. 부터 조회일 전일까지
    # (2016.4.27. 이전 제공요소) 하늘상태, 강수량, 강수형태, 뇌전
    # (2016.4.27. 이후 제공요소) 하늘상태, 강수량, 강수형태, 뇌전, 기온, 습도, 바람(풍향, 풍속, 바람성분)
    # 2021.6.29. 이전 자료는 '구분'의 '(구)초단기예보' 통해 제공
    {
        "name": "구_초단기예보",
        "code": "411",
        "api": "request410",
        "mode": "monthly",
        "reqst_purpose_cd": "F00415",
        "interval": (datetime(2016, 5, 1), datetime(2021, 6, 29)),
        "request_url": "https://data.kma.go.kr/mypage/rmt/callDtaReqstIrods4xxAjax.do",
        "selectType": "2",
        "vars": [
            ("강수형태", "PTY"),
            ("습도", "REH"),
            ("강수", "RN1"),
            ("하늘상태", "SKY"),
            ("기온", "T1H"),
            ("뇌전", "LGT"),
            ("풍향", "VEC"),
            ("풍속", "WSD"),
            ("동서바람성분", "UUU"),
            ("남북바람성분", "VVV"),
        ],
    },
]


# -------------------------------
# 실행
# -------------------------------
import time


def main(login_id: str, password: str, order: str = "asc", config_index: int = None):
    cookie = get_cookie(login_id, password)
    hdr1, hdr2 = make_headers(cookie)
    df_regions = load_region_code(REGION_CODE_PATH)

    if order == "desc":
        df_regions = df_regions.iloc[::-1].reset_index(drop=True)

    configs_to_run = [CONFIGS[config_index]] if config_index is not None else CONFIGS

    for cfg in configs_to_run:
        intervals = gen_intervals(
            cfg["interval"][0],
            cfg["interval"][1],
            mode=("monthly" if cfg["mode"] == "monthly" else "range"),
        )
        base_dir = os.path.join(BASE_SCRIPT_DIR, "data", cfg["name"])

        for _, row in df_regions.iterrows():
            lvl1, lvl2, lvl3, code = (
                row["Level1"],
                row["Level2"],
                row["Level3"],
                row["ReqList_Last"],
            )
            out_dir = os.path.join(base_dir, lvl1, lvl2, lvl3)
            os.makedirs(out_dir, exist_ok=True)

            for start, end in intervals:
                for var_name, var_code in cfg["vars"]:
                    # 추출 대상 파일명
                    expected_csv = f"{lvl3}_{var_name}_{start}_{end}.csv"
                    cat_dir = os.path.join(out_dir, var_name)
                    csv_path = os.path.join(cat_dir, expected_csv)

                    # 이미 추출된 CSV 파일이 있으면 건너뜀
                    if os.path.exists(csv_path):
                        print(f"[{cfg['name']}:{lvl3}] {var_name} {start}~{end} ▶")
                        continue

                    req_body = gen_request_body_common(
                        var_name,
                        var_code,
                        start,
                        end,
                        lvl3,
                        code,
                        cfg["api"],
                        cfg["code"],
                        cfg["reqst_purpose_cd"],
                        cfg["selectType"],
                    )
                    session.post(
                        cfg["request_url"],
                        headers=hdr1,
                        data=req_body,
                    )
                    response = session.post(
                        "https://data.kma.go.kr/data/rmt/downloadZip.do",
                        headers=hdr2,
                        data=gen_download_payload(lvl3, var_name, start, end),
                        stream=True,
                    )

                    if response.status_code == 200:
                        zip_name = f"{lvl3}_{var_name}_{start}_{end}.zip"
                        zip_path = os.path.join(out_dir, zip_name)
                        os.makedirs(os.path.dirname(zip_path), exist_ok=True)
                        with open(zip_path, "wb") as f:
                            for chunk in response.iter_content(8192):
                                f.write(chunk)

                        os.makedirs(cat_dir, exist_ok=True)
                        extracted = False
                        with zipfile.ZipFile(zip_path) as z:
                            for info in z.infolist():
                                try:
                                    filename = info.filename.encode("cp437").decode(
                                        "euc-kr"
                                    )
                                except:
                                    filename = info.filename
                                tgt_path = os.path.join(cat_dir, filename)
                                with open(tgt_path, "wb") as out_f:
                                    out_f.write(z.read(info.filename))
                                extracted = True
                        os.remove(zip_path)
                        if extracted:
                            print(f"[{cfg['name']}:{lvl3}] {var_name} {start}~{end} ✅")
                        else:
                            print(
                                f"[{cfg['name']}:{lvl3}] {var_name} {start}~{end} ⛔ "
                            )
                            cookie = get_cookie(login_id, password)
                            hdr1, hdr2 = make_headers(cookie)
                    else:
                        print(f"  ! 다운로드 실패: {response.status_code}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="기상예보 동네예보 데이터 다운로드")
    parser.add_argument("login_id", type=str, help="로그인 ID")
    parser.add_argument("password", type=str, help="로그인 비밀번호")
    parser.add_argument(
        "--order",
        type=str,
        choices=["asc", "desc"],
        default="asc",
        help="다운로드 순서 (asc: 처음부터, desc: 뒤부터)",
    )
    parser.add_argument(
        "--config-index",
        type=int,
        default=None,
        help="실행할 CONFIGS 인덱스 (0부터 시작). 지정하지 않으면 전체 실행",
    )
    args = parser.parse_args()

    main(
        args.login_id,
        args.password,
        order=args.order,
        config_index=args.config_index,
    )
