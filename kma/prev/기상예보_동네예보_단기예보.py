import os
import zipfile
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta

# -------------------------------
# 기본 설정 및 상수
# -------------------------------
# 세션 생성: 쿠키 등 공유를 위해 사용
session = requests.Session()

korean_labels = [
    "1시간기온",
    "풍속",
    "하늘상태",
    "습도",
    # "일최고기온",
    # "일최저기온",
    # "강수형태",
    # "강수확률",
    # "동서바람성분",
    # "남북바람성분",
    # "1시간강수량",
    # "1시간적설",
    # "파고",
    # "풍향",
]

var_codes = [
    "TMP",
    "WSD",
    "SKY",
    "REH",
    # "TMX",
    # "TMN",
    # "PTY",
    # "POP",
    # "UUU",
    # "VVV",
    # "PCP",
    # "SNO",
    # "WAV",
    # "VEC",
]

# 두 리스트를 zip하여 튜플들의 집합을 만듭니다.
COLUMN_SET = set(zip(korean_labels, var_codes))
# 집합은 순서가 없으므로 리스트로 변환합니다.


# -------------------------------
# 헤더 생성 함수
# -------------------------------
def create_first_header(cookie: str) -> dict:
    return {
        "Accept": "text/plain, */*; q=0.01",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Cookie": cookie,
        "Host": "data.kma.go.kr",
        "Origin": "https://data.kma.go.kr",
        "Referer": "https://data.kma.go.kr/data/rmt/rmtList.do?code=420&pgmNo=574",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }


def create_second_header(cookie: str) -> dict:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": cookie,
        "Host": "data.kma.go.kr",
        "Origin": "https://data.kma.go.kr",
        "Referer": "https://data.kma.go.kr/data/rmt/rmtList.do?code=420&pgmNo=574",
        "Sec-Fetch-Dest": "iframe",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }


# -------------------------------
# 날짜 구간 생성 함수
# -------------------------------
def generate_date_intervals(
    start_date: datetime, end_date: datetime, delta_months: int = 1
):
    """
    start_date부터 end_date까지 delta_months 개월 간격의 (시작, 종료) 날짜 구간 리스트를 생성합니다.
    각 날짜는 'YYYYMMDD' 형식의 문자열로 반환됩니다.
    """
    intervals = []
    current_start = start_date
    while current_start < end_date:
        current_end = current_start + relativedelta(months=delta_months)
        if current_end > end_date:
            current_end = end_date
        intervals.append(
            (current_start.strftime("%Y%m%d"), current_end.strftime("%Y%m%d"))
        )
        current_start = current_end
    return intervals


# -------------------------------
# 요청 본문 생성 함수
# -------------------------------
def generate_first_request_body(
    column: tuple, start: str, end: str, stnm: str, 동코드
) -> dict:
    data_code = "424"  # 지역 바뀌어도 이 값은 변하지 않음
    var3 = 동코드
    return {
        "apiCd": "request420",
        "data_code": data_code,
        "hour": "",
        "pageIndex": "1",
        "from": start,
        "to": end,
        "file_size": "",
        "recordCountPerPage": "10",
        "txtVar1Nm": column[0],  # 한글 라벨 사용
        "selectType": "1",
        "startDt": start[:4],
        "startMt": start[4:6],
        "endDt": end[:4],
        "endMt": end[4:6],
        "from_": start,
        "to_": end,
        "var1": column[1],
        "var3": var3,
        "stnm": stnm,
        "elcd": column[0],  # 필요에 따라 column[1]로 변경 가능
        "strtm": start,
        "endtm": end,
        "req_list": f"{start}|{end}|{data_code}|{column[1]}|{var3}",
    }


def generate_second_request_body(stnm: str, column: str, start: str, end: str) -> str:
    return f"{stnm}_{column}_{start}_{end}.csv"


# -------------------------------
# 쿠키 및 헤더 설정
# -------------------------------
cookie_str = "loginId=shdbtjd8@gmail.com; JSESSIONID=kjXkvpuAruyJKX8ZHfUdoFBYs17Isqotu1CsvWl1kHZCdtQUlnVggu84GD0j9HYh.was01_servlet_engine5"
first_header = create_first_header(cookie_str)
second_header = create_second_header(cookie_str)


# -------------------------------
# 동네 이름 및 디렉토리 생성
# -------------------------------
동이름 = "정선읍"
동코드 = "89_123"
BASE_DIR = "data/data"
dong_dir = os.path.join(BASE_DIR, 동이름)
os.makedirs(dong_dir, exist_ok=True)


# -------------------------------
# 날짜 설정 (예: 2025-03-14 ~ 2025-03-18)
# -------------------------------
start_date_obj = datetime(2021, 1, 1)
end_date_obj = datetime(2021, 12, 31)
date_intervals = generate_date_intervals(start_date_obj, end_date_obj)

# -------------------------------
# 데이터 생성 및 파일 다운로드/압축해제 루프
# -------------------------------
for start_date, end_date in date_intervals:
    for column in list(COLUMN_SET):  # 예시로 첫 3개 카테고리에 대해 실행
        # 1. 데이터 생성 요청
        request_body = generate_first_request_body(
            column, start_date, end_date, 동이름, 동코드
        )
        url_generation = (
            "https://data.kma.go.kr/mypage/rmt/callDtaReqstIrods4xxNewAjax.do"
        )
        print(
            "데이터 생성 요청 중...", f"컬럼: {column} 구간: {start_date} ~ {end_date}"
        )
        response_generation = session.post(
            url_generation, headers=first_header, data=request_body
        )
        print("데이터 생성 요청 상태 코드:", response_generation.status_code)
        print("데이터 생성 요청 응답:", response_generation.text)

        # 2. 파일 다운로드 요청
        url_download = "https://data.kma.go.kr/data/rmt/downloadZip.do"
        data_download = {
            "downFile": generate_second_request_body(
                동이름, column[0], start_date, end_date
            )
        }
        print("파일 다운로드 요청 중...")
        response_download = session.post(
            url_download, headers=second_header, data=data_download, stream=True
        )

        if response_download.status_code == 200:
            # zip 파일은 동 디렉토리 하위에 저장
            zip_filename = f"{동이름}_{column[0]}_{start_date}_{end_date}.zip"
            zip_filepath = os.path.join(dong_dir, zip_filename)
            with open(zip_filepath, "wb") as f:
                for chunk in response_download.iter_content(chunk_size=8192):
                    if chunk:
                        print(chunk)
                        f.write(chunk)
            print("파일 다운로드 완료:", zip_filepath)

            # 3. 압축 해제: data/동이름/카테고리 디렉토리 하위에 압축 해제
            category_dir = os.path.join(dong_dir, column[0])
            os.makedirs(category_dir, exist_ok=True)

            with zipfile.ZipFile(zip_filepath, "r") as zip_ref:
                for info in zip_ref.infolist():
                    try:
                        # zip 내부 파일 이름은 기본적으로 cp437 인코딩되어 있을 수 있으므로 euc-kr로 디코딩
                        fixed_filename = info.filename.encode("cp437").decode("euc-kr")
                    except Exception as e:
                        print("디코딩 실패:", info.filename, e)
                        fixed_filename = info.filename
                    target_path = os.path.join(category_dir, fixed_filename)
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with open(target_path, "wb") as out_file:
                        out_file.write(zip_ref.read(info.filename))
                    print("추출 완료:", fixed_filename)

            print(
                f"압축 해제 완료. CSV 파일들은 '{category_dir}' 폴더에 저장되었습니다."
            )
        else:
            print("파일 다운로드 실패, 상태 코드:", response_download.status_code)
