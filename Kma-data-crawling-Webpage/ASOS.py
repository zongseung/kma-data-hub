import os
import csv
import time
import socket
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import unquote  # ← 여기에 추가

# 1) CSV에서 코드↔이름 매핑 생성
def load_station_map(csv_path: str) -> (dict[str, str], set[str]):
    df = pd.read_csv(csv_path, dtype=str)
    code2name = dict(zip(df['code'], df['name']))
    name2code = dict(zip(df['name'], df['code']))
    codes = set(df['code'])
    return code2name, name2code, codes

# 2) JSON/HTTP 요청 + 페이징
def fetch_asos_data(
    service_key: str,
    start: str,
    end: str,
    station_id: str,
    max_retries: int = 3,
    per_page: int = 999
) -> pd.DataFrame:
    service_key = unquote(unquote(service_key))
    url = 'http://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList'
    all_records: list[dict] = []
    page_no = 1
    while True:
        params = {
            'serviceKey': service_key,
            'pageNo': str(page_no),
            'numOfRows': str(per_page),
            'dataType': 'JSON',
            'dataCd': 'ASOS',
            'dateCd': 'HR',
            'startDt': start,
            'startHh': '00',
            'endDt': end,
            'endHh': '23',
            'stnIds': station_id
        }
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                break
            except (requests.RequestException, socket.error, ValueError) as e:
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                else:
                    print(f"❌ 요청 실패: station_id={station_id}, page={page_no}, error={e}")
                    return pd.DataFrame()
        items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        if not items:
            break
        all_records.extend(items)
        if len(items) < per_page:
            break
        page_no += 1
    df = pd.DataFrame(all_records)
    if not df.empty:
        # 컬럼명 매핑
        df = df.rename(columns={
            'tm': 'time',
            'stnId': 'station_id',
            'stnNm': 'station_name',
            'ta': 'temperature',
            'ws': 'wind_speed',
            'wd': 'wind_direction',
            'hm': 'humidity',
            'pv': 'precipitation',
            'td': 'dew_point',
            'pa': 'pressure',
            'ps': 'sea_pressure',
            'dsnw': 'snow_depth',
            'ts': 'ground_temp'
        })
        df['time'] = pd.to_datetime(df['time'])
    return df

# 3) 사용자 지정 복수 지역 데이터 수집
def select_data(
    region_keys: list[str],
    start: str,
    end: str,
    csv_path: str = '/app/data/asos.csv',
    exclude: set[str] = None
) -> pd.DataFrame:
    code2name, name2code, codes = load_station_map(csv_path)
    service_key = "iCNxo2r0TdZnnV63/ItO+QrOUqJakXCxx/m20BsCp53DGZzJMDd1/7jOGLYQE+Sn+1EQeSeIhUsTIyQ5dYgy4Q=="
    if not service_key:
        raise RuntimeError('환경변수 SERVICE_KEY가 설정되어 있지 않습니다.')

    result_df = pd.DataFrame()
    exclude = exclude or set()
    for key in region_keys:
        if key in exclude:
            print(f"⚠️ 제외된 지역: {key}")
            continue
        if key in name2code:
            station_id = name2code[key]
        elif key in codes:
            station_id = key
        else:
            print(f"⚠️ 잘못된 지역: {key}")
            continue

        print(f"▶️ 수집 시작: station_id={station_id} ({key}), {start}~{end}")
        df = fetch_asos_data(service_key, start, end, station_id)
        if df.empty:
            print(f"❌ 데이터 없음: {station_id} ({key})")
        else:
            df['region_key'] = key
            result_df = pd.concat([result_df, df], ignore_index=True)
            print(f"✅ 수집 완료: {station_id} ({key}), rows={len(df)}")
        time.sleep(1)
    return result_df

# 4) 스크립트 실행 예시
if __name__ == '__main__':
    regions_input = input('지역명/코드를 쉼표로 구분해 입력: ')
    region_keys = [r.strip() for r in regions_input.split(',') if r.strip()]
    start_date = input('시작일 (YYYYMMDD): ')
    end_date = input('종료일 (YYYYMMDD): ')
    exclude_codes = {'00'}

    df_all = select_data(region_keys, start_date, end_date, exclude=None)
    if not df_all.empty:
        out_file = f"collected_{start_date}_{end_date}_{'_'.join(region_keys)}.csv"
        df_all.to_csv(out_file, index=False, encoding='utf-8-sig')
        print(f"▶️ 저장 완료: {out_file}")
    else:
        print('수집된 데이터가 없습니다.')
