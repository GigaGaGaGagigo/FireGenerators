import json
from collections import defaultdict
from pathlib import Path

# 토픽 매핑
topic_id_map = {
    "경영": 1,
    "경제": 2,
    "공공": 3,
    "과학": 4,
    "금융": 5,
    "사회": 6,
    "산업": 7,
    "동향": 8
}

# 분석할 JSON 파일
files = {
    "경제": "contents_경제.json",
    "사회": "contents_사회.json",
    "과학": "contents_과학.json",
    "금융": "contents_금융.json"
}

# 집계용 변수
topic_counts = defaultdict(int)  # 토픽별 총 개수
level_counts = defaultdict(lambda: defaultdict(int))  # 토픽별 난이도별 개수
style_counts = defaultdict(lambda: defaultdict(int))  # 토픽별 스타일별 개수
total_level_counts = defaultdict(int)  # 난이도별 전체 합계
total_style_counts = defaultdict(int)  # 스타일별 전체 합계

# 데이터 집계
for topic_name, file_path in files.items():
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"⚠️ {file_path} 없음, 건너뜀")
        continue

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for card in data:
        topic_id = topic_id_map[topic_name]
        level = card.get("level", "Unknown")
        style = card.get("style", "Unknown")

        topic_counts[topic_id] += 1
        level_counts[topic_id][level] += 1
        style_counts[topic_id][style] += 1

        total_level_counts[level] += 1
        total_style_counts[style] += 1

# 📊 출력
print("📊 토픽별 총 개수:")
for topic_id, count in topic_counts.items():
    print(f"  {topic_id}: {count}")

print("\n📊 토픽별 난이도별 개수:")
for topic_id, levels in level_counts.items():
    print(f"  {topic_id}:")
    for level, count in levels.items():
        print(f"    {level}: {count}")

print("\n📊 토픽별 스타일별 개수:")
for topic_id, styles in style_counts.items():
    print(f"  {topic_id}:")
    for style, count in styles.items():
        print(f"    {style}: {count}")

print("\n📊 난이도별 전체 합계:")
for level, count in total_level_counts.items():
    print(f"  {level}: {count}")

print("\n📊 스타일별 전체 합계:")
for style, count in total_style_counts.items():
    print(f"  {style}: {count}")