# databases.py

import sqlite3
import os
import csv
from typing import List, Dict

class RegionDatabase:
    def __init__(self, db_path: str = "data/local_codes.db"):
        self.db_path = db_path
        # 1) data/ 디렉터리 확보
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # 2) 테이블이 없으면 만들고, 동시에 시드
        if not self._table_exists("regions"):
            self._init_database()

    def _table_exists(self, table_name: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        exists = cur.fetchone() is not None
        conn.close()
        return exists

    def _init_database(self):
        """
        1) regions 테이블 생성  
        2) CSV(또는 다른 소스)에서 한 번만 읽어와 INSERT
        """
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # (1) 테이블 생성
        cur.execute("""
        CREATE TABLE IF NOT EXISTS regions (
            Level1        TEXT NOT NULL,
            Level2        TEXT NOT NULL,
            Level3        TEXT NOT NULL,
            ReqList_Last  TEXT PRIMARY KEY
        );
        """)

        # (2) CSV 파일에서 데이터 로드
        #    프로젝트 루트에 scripts/seed_regions.csv 같은 이름으로 두었다고 가정
        csv_path = os.path.join(os.path.dirname(__file__), "scripts", "seed_regions.csv")
        if os.path.exists(csv_path):
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                # 헤더 스킵 (헤더: Level1,Level2,Level3,ReqList_Last 순)
                next(reader, None)
                for row in reader:
                    level1, level2, level3, code = row
                    cur.execute(
                        "INSERT OR IGNORE INTO regions (Level1, Level2, Level3, ReqList_Last) VALUES (?, ?, ?, ?)",
                        (level1, level2, level3, code)
                    )
        else:
            # 만약 CSV가 없다면, 이미 외부에서 미리 채워진 DB를 사용중인 경우
            pass

        conn.commit()
        conn.close()

    def get_available_regions(self, search_term: str = "") -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        cur  = conn.cursor()
        like = f"%{search_term}%"
        if search_term:
            cur.execute("""
            SELECT Level1, Level2, Level3, ReqList_Last
              FROM regions
             WHERE Level1 LIKE ?
                OR Level2 LIKE ?
                OR Level3 LIKE ?
             ORDER BY Level1, Level2, Level3
            """, (like, like, like))
        else:
            cur.execute("""
                SELECT Level1, Level2, Level3, ReqList_Last
                  FROM regions
               ORDER BY Level1, Level2, Level3
            """)
        rows = cur.fetchall()
        return [
            {
                "level1": r[0],
                "level2": r[1],
            "level3": r[2],
            "code":   r[3]
        }
        for r in rows
    ]

    def search_regions(self, query):
        """지역명으로 검색하여 결과 반환"""
        DB_PATH = self.db_path
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        try:
            # LIKE 검색으로 부분 일치 검색
            search_query = f"%{query}%"
            cursor.execute("""
                SELECT ReqList_Last, Level1
                FROM regions 
                WHERE Level1 LIKE ? 
                ORDER BY 
                    CASE 
                        WHEN Level1 = ? THEN 1
                        WHEN Level1 LIKE ? THEN 2
                        ELSE 3
                    END,
                    Level1
                LIMIT 20
            """, (search_query, query, f"{query}%"))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'code': row[0],
                    'name': row[1],

                })
            
            return results
            
        except Exception as e:
            print(f"지역 검색 오류: {e}")
            return []
        finally:
            conn.close()

