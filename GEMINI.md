
# Project Overview

This project, FIREgenerator, is a Python-based web application designed to provide personalized financial product recommendations. It utilizes a chatbot interface to gather user information, including their financial goals, risk tolerance, and interests. This data is then used to generate tailored recommendations for financial products and content.

The application is built with the following technologies:

*   **Backend:** Python with Streamlit for the web interface.
*   **Natural Language Processing:** `langchain` and `google-generativeai` are used for the chatbot functionality.
*   **Authentication and Database:** Supabase is used for user authentication (Google OAuth) and data storage.
*   **Frontend:** The UI is created with Streamlit components and custom CSS for styling.

The project is structured as a multi-page Streamlit application with different views for regular users and administrators.

# Building and Running

To run this project, you need to have Python and the required packages installed.

1.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Set up environment variables:**
    This project uses Supabase for authentication and database services. You will need to create a `.env` file in the root directory and add your Supabase URL and key:
    ```
    SUPABASE_URL=your_supabase_url
    SUPABASE_KEY=your_supabase_key
    ```

3.  **Run the application:**
    ```bash
    streamlit run my_app/app.py
    ```

# Development Conventions

*   **Project Structure:** The main application logic is in `my_app/app.py`. The different pages of the application are located in the `my_app/ui/` directory. Each page is a self-contained module with a `render()` function that displays the content.
*   **Adding New Pages:** To add a new page, create a new Python file in the `my_app/ui/` directory. Then, add the page to the `USER_MENUS` dictionary in `my_app/app.py` to make it appear in the sidebar navigation.
*   **Styling:** Global CSS styles are defined in the `apply_global_styles()` function in `my_app/app.py`.
*   **Authentication:** Authentication is handled by Supabase. The `check_auth_params()` function in `my_app/app.py` processes the OAuth callback from Google.
*   **State Management:** The application uses Streamlit's session state (`st.session_state`) to maintain user data and application state across different pages.

# 리팩토링 분석 (2025-08-23)

## `my_app/ui/chatbot/` 폴더 리팩토링

챗봇 모듈에 대한 주요 리팩토링이 수행되어 구조적으로 큰 개선이 이루어졌습니다.

### 1. UI 로직 단순화
- **변경점**: `handlers/answer_handler.py`를 제거하고, `chatbot.py` 내에 `answer_callback` 함수를 인라인으로 구현했습니다.
- **평가**: 긍정적. UI 컴포넌트와 이벤트 핸들러를 같은 위치에 둠으로써 코드의 응집도를 높이고 로직을 단순화했습니다.

### 2. 서비스 레이어 도입
- **변경점**: 콜백 기반의 옵저버 패턴을 사용하는 `services/profile_service.py`를 도입했습니다.
- **평가**: 매우 뛰어남. UI와 데이터 영속성 계층(Supabase)을 분리하여 관심사 분리 원칙을 잘 따르고 있으며, 앱의 확장성과 유지보수성을 크게 향상시켰습니다.

### 3. 데이터 영속성 로직 통합
- **관찰**: `utils/profile_updater.py`와 새로운 `services/profile_service.py`의 역할이 일부 중첩됩니다.
- **권장 사항**: 모든 데이터베이스 업데이트 로직을 `profile_service.py`로 통합하여 데이터 영속성을 위한 진입점을 단일화하는 것을 권장합니다. `profile_updater.py`의 기능은 서비스의 내부 구현으로 간주하고, 최종적으로는 해당 파일을 제거하여 구조를 더 명확하게 만드는 것이 좋습니다.

### 총평
매우 성공적인 리팩토링입니다. 코드베이스가 더 견고하고 모듈화되었으며 유지보수하기 쉬워졌습니다. 다음 단계로 서비스 기반 아키텍처로의 전환을 완료하는 것이 좋습니다.

# User Preferences

- 제가 요청하기 전까지는 코드를 제안만해주시고, 수정은 진행하지 말아주세요.
