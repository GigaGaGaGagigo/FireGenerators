-- 1. user_contents_log 테이블 생성
CREATE TABLE user_contents_log (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id uuid NOT NULL,
    contents_id uuid NOT NULL,
    content_title text NOT NULL,
    original_content text NOT NULL,
    ai_explanation text NOT NULL,
    user_level text NOT NULL CHECK (user_level IN ('Beginner', 'Intermediate', 'Advanced')),
    recommendation_source text DEFAULT 'unknown',
    recommendation_rank integer,
    user_context jsonb NOT NULL DEFAULT '{}',
    feedback_type text CHECK (feedback_type IN ('positive', 'neutral', 'negative')),
    feedback_details jsonb DEFAULT '{}',
    feedback_at timestamptz,
    explanation_length integer GENERATED ALWAYS AS (length(ai_explanation)) STORED,
    original_content_length integer GENERATED ALWAYS AS (length(original_content)) STORED,
    viewed_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- 2. 인덱스 생성 (조회 최적화)
CREATE INDEX idx_user_contents_log_user_id ON user_contents_log(user_id);
CREATE INDEX idx_user_contents_log_contents_id ON user_contents_log(contents_id);
CREATE INDEX idx_user_contents_log_viewed_at ON user_contents_log(viewed_at DESC);

-- 3. RLS 활성화
ALTER TABLE user_contents_log ENABLE ROW LEVEL SECURITY;

-- 4. 외래키 제약조건 추가 (다른 테이블은 수정 X, 참조만)
ALTER TABLE user_contents_log
  ADD CONSTRAINT fk_user_contents_log_user_id
  FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE;

ALTER TABLE user_contents_log
  ADD CONSTRAINT fk_user_contents_log_contents_id
  FOREIGN KEY (contents_id) REFERENCES contents(id) ON DELETE CASCADE;