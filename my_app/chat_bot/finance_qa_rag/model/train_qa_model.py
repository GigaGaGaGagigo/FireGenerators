from datasets import load_dataset
from transformers import BertTokenizerFast, BertForQuestionAnswering, TrainingArguments, Trainer
import torch

model_name = "monologg/kobert"
tokenizer = BertTokenizerFast.from_pretrained(model_name)
model = BertForQuestionAnswering.from_pretrained(model_name)

# 데이터 로드
dataset = load_dataset(
    "json",
    data_files="my_app/chat_bot/finance_qa_rag/data/squad_terms.json",
    field="data"
)

# 전처리 함수 (간단한 버전)
def preprocess(example):
    context = example["paragraphs"][0]["context"]
    question = example["paragraphs"][0]["qas"][0]["question"]
    answer = example["paragraphs"][0]["qas"][0]["answers"][0]
    start_char = answer["answer_start"]
    end_char = start_char + len(answer["text"])

    inputs = tokenizer(
        question,
        context,
        truncation="only_second",
        max_length=512,
        return_offsets_mapping=True,
        padding="max_length"
    )

    # 문맥 내에서 답 위치 파악
    offsets = inputs["offset_mapping"]
    sequence_ids = inputs.sequence_ids()

    token_start_index = 0
    while sequence_ids[token_start_index] != 1:
        token_start_index += 1

    token_end_index = len(inputs["input_ids"]) - 1
    while sequence_ids[token_end_index] != 1:
        token_end_index -= 1

    # 정답 토큰 인덱스 찾기
    start_pos = token_start_index
    end_pos = token_end_index
    for i in range(token_start_index, token_end_index + 1):
        if offsets[i][0] <= start_char and offsets[i][1] >= start_char:
            start_pos = i
        if offsets[i][0] <= end_char and offsets[i][1] >= end_char:
            end_pos = i

    inputs["start_positions"] = start_pos
    inputs["end_positions"] = end_pos
    inputs.pop("offset_mapping")

    return inputs

# 전처리
tokenized_dataset = dataset["train"].map(preprocess, batched=False)

# 학습 설정
args = TrainingArguments(
    output_dir="my_app/chat_bot/finance_qa_rag/model/kobert-qa",
    per_device_train_batch_size=8,
    num_train_epochs=3,
    logging_dir="./logs",
    logging_steps=10,
    save_strategy="epoch"
)

# Trainer 정의 및 학습
trainer = Trainer(
    model=model,
    args=args,
    train_dataset=tokenized_dataset
)

trainer.train()

# 저장
model.save_pretrained("my_app/chat_bot/finance_qa_rag/model/kobert-qa")
tokenizer.save_pretrained("my_app/chat_bot/finance_qa_rag/model/kobert-qa")
