# 프로젝트 구조 분석 (FireGenerators)

이 문서는 `my_app/app.py`를 기반으로 FireGenerators 애플리케이션의 아키텍처, 디렉토리 구조, 핵심 로직을 설명합니다.

## 1. 개요

본 프로젝트는 **Streamlit** 프레임워크를 사용하여 구축된 **단일 페이지 애플리케이션(SPA)** 입니다. 백엔드 서비스로는 **Supabase**를 활용하여 사용자 인증(Google OAuth)과 데이터베이스(프로필 관리)를 처리합니다.

주요 특징은 다음과 같습니다.
- **역할 기반 접근 제어 (RBAC)**: `User`와 `Admin` 역할에 따라 다른 메뉴와 페이지를 제공합니다.
- **커스텀 페이지 라우팅**: Streamlit의 기본 멀티페이지 앱 기능 대신, 세션 상태(`st.session_state`)를 이용한 자체 라우팅 시스템을 구현했습니다.
- **모듈화된 UI**: 각 페이지의 UI는 `ui/` 디렉토리 내의 개별 Python 파일로 분리되어 관리됩니다.

## 2. 디렉토리 구조

`app.py` 코드에서 유추할 수 있는 프로젝트의 디렉토리 구조는 다음과 같습니다.

```
FireGenerators/
├── my_app/
│   ├── app.py              # 메인 애플리케이션 로직, 라우팅, 인증 처리
│   ├── assets/
│   │   ├── FIRE_LOGO_large.png
│   │   └── FIREgen_horizontal_logo_edit.png
│   └── ui/
│       ├── chatbot/
│       │   └── chatbot_sample.py
│       ├── level_quiz/
│       │   └── quiz.py
│       ├── contents/
│       │   └── recomendation_contents.py
│       ├── recommendation/
│       │   └── recommendation.py
│       ├── simulation/
│       │   └── simulation_sample.py
│       ├── analysis/
│       │   └── analysis.py
│       └── settings/
│           └── settings_sample.py
└── PROJECT_STRUCTURE.md    # (본 문서)
```

- **`my_app/app.py`**: 애플리케이션의 진입점(Entry Point)입니다. 모든 핵심 로직이 여기에 포함됩니다.
- **`my_app/assets/`**: 로고 이미지와 같은 정적 파일을 저장합니다.
- **`my_app/ui/`**: 각 페이지의 UI를 구성하는 `render()` 함수를 포함한 파이썬 모듈들이 위치합니다. `app.py`의 `route_to_page` 함수가 이곳의 모듈을 동적으로 임포트하여 사용합니다.

## 3. 핵심 로직 및 흐름

### 3.1. 애플리케이션 실행 (`main` 함수)

1.  **페이지 설정**: `st.set_page_config()`로 앱의 기본 레이아웃을 설정합니다.
2.  **세션 초기화**: `st.session_state`에 `role`, `current_page` 등 필수 키가 없으면 초기화합니다.
3.  **인증 콜백 처리**: `check_auth_params()`를 호출하여 Google 로그인 후 리디렉션된 경우인지 확인하고, 인증 코드를 세션으로 교환합니다.
4.  **인증 분기**: `st.session_state.role` 값의 유무에 따라 `main_app()` (로그인 후) 또는 `login()` (로그인 전) 함수를 실행합니다.

### 3.2. 인증 (Authentication)

- **로그인**: `login()` 함수가 "Sign in with Google" 버튼을 표시합니다. 버튼 클릭 시 Supabase의 `sign_in_with_oauth`를 호출하여 Google 로그인 페이지로 리디렉션합니다.
- **콜백 처리**: `check_auth_params()` 함수가 URL 쿼리 파라미터의 `code`를 감지하여 Supabase의 `exchange_code_for_session`을 통해 사용자 세션을 생성하고 `st.session_state`에 저장합니다.
- **프로필 동기화**: 최초 로그인 시, Supabase의 `profiles` 테이블에 사용자 정보를 생성하고 기본 역할(`User`)을 부여합니다.
- **로그아웃**: `logout()` 함수가 Supabase 세션을 파기하고 로컬 `st.session_state`를 정리한 후, `st.rerun()`을 통해 로그인 페이지로 이동시킵니다.

### 3.3. 페이지 라우팅 (Custom Routing)

이 앱은 `st.session_state.current_page` 값을 기준으로 표시할 페이지를 결정합니다.

1.  **사이드바 렌더링**: `render_sidebar()` 함수가 `streamlit-option-menu`를 사용해 사이드바 메뉴를 생성합니다. 메뉴는 `USER_MENUS` 설정에 따라 현재 사용자의 역할에 맞게 동적으로 구성됩니다.
2.  **페이지 상태 변경**: 사용자가 메뉴를 클릭하면, 선택된 페이지의 키(`chatbot`, `quiz` 등)가 `st.session_state.current_page`에 저장되고 `st.rerun()`이 호출됩니다.
3.  **페이지 렌더링**: `route_to_page()` 함수가 `st.session_state.current_page` 값을 확인하고, `if/elif` 문을 통해 해당 페이지의 `render()` 함수를 동적으로 `import`하여 호출합니다. 예를 들어 `current_page`가 "quiz"이면 `ui.level_quiz.quiz` 모듈의 `render()` 함수를 실행합니다.

## 4. 개발 가이드 요약

`app.py` 상단의 개발 가이드에 명시된 것처럼, 새로운 페이지를 추가하는 과정은 다음과 같습니다.

1.  **파일 생성**: `ui/` 폴더 아래에 새 페이지를 위한 Python 파일을 만듭니다. (예: `ui/new_feature/new_page.py`) 이 파일에는 `render()` 함수가 반드시 포함되어야 합니다.
2.  **메뉴 설정**: `app.py`의 `USER_MENUS` 딕셔너리에 새로운 메뉴 항목 `("표시될 이름", "페이지 키")`을 추가합니다.
3.  **아이콘 설정**: `PAGE_ICONS` 딕셔너리에 `페이지 키: "아이콘 이름"` 쌍을 추가합니다.
4.  **라우팅 로직 추가**: `route_to_page()` 함수에 새로운 `elif current_page == "페이지 키":` 분기문을 추가하여 새로 만든 `render()` 함수를 호출하도록 연결합니다.
