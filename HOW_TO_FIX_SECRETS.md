# Streamlit Secrets 설정 및 Supabase 오류 해결 가이드

`Supabase 초기화 오류: 'st.secrets has no key "supabase"'` 오류는 Streamlit 앱이 Supabase 접속에 필요한 인증 정보를 찾지 못해 발생하는 문제입니다.

이 문제를 해결하려면 프로젝트에 `secrets.toml` 파일을 만들어 Supabase 접속 정보를 추가해야 합니다.

## 해결 단계

### 1. `.streamlit` 폴더 생성

프로젝트의 최상위 폴더(`FireGenerators`) 안에 `.streamlit`이라는 이름의 폴더를 생성합니다.

-   **위치**: `/Users/min/Desktop/FireGenerators/.streamlit/`

> **참고**: 이름이 점(`.`)으로 시작하는 폴더는 숨김 처리될 수 있습니다. Finder에서 `Cmd + Shift + .` 키를 누르면 숨김 파일을 보거나 숨길 수 있습니다.

### 2. `secrets.toml` 파일 생성

방금 만든 `.streamlit` 폴더 안에 `secrets.toml` 이라는 이름의 파일을 생성합니다.

-   **전체 경로**: `/Users/min/Desktop/FireGenerators/.streamlit/secrets.toml`

### 3. `secrets.toml` 파일에 내용 추가

생성한 `secrets.toml` 파일을 열고 아래 내용을 복사하여 붙여넣으세요. `YOUR_SUPABASE_URL`과 `YOUR_SUPABASE_ANON_KEY` 부분은 실제 값으로 변경해야 합니다.

```toml
# .streamlit/secrets.toml

# Supabase 접속 정보
[supabase]
url = "YOUR_SUPABASE_URL"
key = "YOUR_SUPABASE_ANON_KEY"

# 종목 추천(stock_rec) 앱에서 사용하는 사용자 프로필 정보
# 필요에 따라 내용을 수정하세요.
USER_PROFILE_JSON = '''
{
  "name": "김투자",
  "age": 35,
  "investment_style": "가치 투자",
  "risk_tolerance": "중간",
  "interested_sectors": ["기술", "헬스케어"]
}
'''
```

> **참고**: `USER_PROFILE_JSON`은 `stock_rec` 앱에서 사용하는 값이므로 함께 추가했습니다.

### 4. Supabase URL 및 Key 확인 방법

1.  [Supabase 프로젝트 대시보드](https://app.supabase.com/)에 로그인합니다.
2.  해당 프로젝트를 선택합니다.
3.  왼쪽 메뉴에서 **Settings** (톱니바퀴 아이콘) > **API** 로 이동합니다.
4.  **Project API keys** 섹션에서 다음 두 값을 복사하여 `secrets.toml` 파일에 붙여넣습니다.
    *   **URL**: `url` 값으로 사용합니다.
    *   **anon public key**: `key` 값으로 사용합니다.

### 5. 앱 재실행

`secrets.toml` 파일을 저장한 후, 터미널에서 실행 중인 Streamlit 앱을 `Ctrl + C`로 종료하고 다시 실행합니다.

```bash
# FireGenerators 폴더에서 실행
streamlit run my_app/app.py
```

이제 오류 없이 앱이 정상적으로 실행될 것입니다.

---

### **⚠️ 중요: 보안 경고**

`secrets.toml` 파일에는 민감한 정보가 포함되어 있으므로, **절대로 Git과 같은 버전 관리 시스템에 올리면 안 됩니다.** 프로젝트에 `.gitignore` 파일이 있다면, 아래와 같이 `.streamlit/` 폴더를 추가하여 Git 추적에서 제외하세요.

```
# .gitignore

# Streamlit secrets
.streamlit/
```
