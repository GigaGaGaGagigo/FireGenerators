import json
import os
from collections import defaultdict

# 입력 JSON 파일 경로 (해당 파일명으로 바꾸기)
input_file = "sorted_by_subject_data.json"

# 출력 디렉토리 (없으면 생성됨)
output_dir = "output_by_category"
os.makedirs(output_dir, exist_ok=True)

# JSON 파일 불러오기
with open(input_file, "r", encoding="utf-8") as f:
    data = json.load(f)

# 카테고리별로 분류
categories = defaultdict(list)
for item in data:
    category = item.get("주제", "기타")
    categories[category].append(item)

# 각 카테고리별로 JSON 파일 저장
for category, items in categories.items():
    filename = f"{category}.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"✅ {filename} 저장 완료 ({len(items)}개 항목)")