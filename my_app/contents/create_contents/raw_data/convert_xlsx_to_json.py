import pandas as pd
import json
from collections import defaultdict

# 1. 엑셀 파일 불러오기
excel_path = "dictionary_data.xlsx"  # 엑셀 파일 경로
df = pd.read_excel(excel_path, sheet_name="Sheet1")

# 2. 필요한 컬럼만 추출
df = df[['순번', '주제', '용어', '설명']]

# 3. JSON으로 임시 저장 (레코드 형식)
json_temp_path = "dictionary_data.json"
df.to_json(json_temp_path, orient="records", force_ascii=False)

# 4. JSON 파일 불러오기
with open(json_temp_path, "r", encoding="utf-8") as f:
    cards = json.load(f)

# 5. 주제별로 그룹화
grouped = defaultdict(list)
for card in cards:
    grouped[card["주제"]].append(card)

# 6. 주제별 정렬된 리스트로 변환 + 요약 정보 저장
sorted_cards = []
summary = {}

for subject in sorted(grouped.keys()):
    cards_in_subject = grouped[subject]
    sorted_cards.extend(cards_in_subject)
    summary[subject] = len(cards_in_subject)

# 7. 정렬된 JSON 저장
json_sorted_path = "sorted_by_subject_data.json"
with open(json_sorted_path, "w", encoding="utf-8") as f:
    json.dump(sorted_cards, f, ensure_ascii=False, indent=4)

# 8. 요약 출력
print("📊 주제별 용어 개수 요약:")
for subject, count in summary.items():
    print(f"- {subject}: {count}개")