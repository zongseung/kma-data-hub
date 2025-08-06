import csv

# 파일 경로
regions_file = "regions.csv"
extracted_file = "extracted_data.csv"
output_file = "merged_by_rowww.csv"

# 두 파일을 모두 읽어서 리스트로 저장
with open(regions_file, encoding="utf-8-sig", newline="") as rf, open(
    extracted_file, encoding="utf-8-sig", newline=""
) as ef:
    regions_reader = list(csv.DictReader(rf))
    extracted_reader = list(csv.DictReader(ef))

# 병합할 행 수: 둘 중 짧은 쪽 기준
n_rows = min(len(regions_reader), len(extracted_reader))
merged_rows = []

for i in range(n_rows):
    r = regions_reader[i]
    e = extracted_reader[i]

    # regions.csv 쪽 Level3
    lvl3 = r.get("Level3", "").strip()

    # extracted_data.csv 쪽 Location에서 동 추출
    loc_parts = e.get("Location", "").strip('"').split(",")
    dong = loc_parts[1].strip() if len(loc_parts) >= 2 else ""

    # 불일치 경고
    if lvl3 != dong:
        print(
            f"[Warning] row {i+1}: regions Level3='{lvl3}' vs extracted dong='{dong}'"
        )

    merged_rows.append(
        {
            "Level1": r.get("Level1", "").strip(),
            "Level2": r.get("Level2", "").strip(),
            "Level3": lvl3,
            "ReqList_Last": e.get("ReqList_Last", "").strip(),
        }
    )

# 결과 쓰기
with open(output_file, "w", encoding="utf-8-sig", newline="") as of:
    fieldnames = ["Level1", "Level2", "Level3", "ReqList_Last"]
    writer = csv.DictWriter(of, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(merged_rows)

print(f"총 {len(merged_rows)}개 행을 '{output_file}'에 저장했습니다.")
