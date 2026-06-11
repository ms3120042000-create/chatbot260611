# 💬 Chatbot

OpenAI API를 사용하는 Streamlit 기반 챗봇 웹앱입니다.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://chatbot-template.streamlit.app/)

## 기능

- **모델 선택** — `gpt-4o-mini`, `gpt-4o`, `gpt-3.5-turbo` 중 선택
- **Temperature 조절** — 창의성 슬라이더 (0.0 ~ 2.0)
- **Max Tokens 조절** — 최대 응답 길이 설정 (256 ~ 4096)
- **스트리밍 응답** — 실시간 타이핑 효과
- **대화 히스토리** — 세션 내 전체 컨텍스트 유지
- **채팅 기록 내보내기** — `.txt` 또는 `.json` 파일로 다운로드
- **대화 초기화** — 사이드바 버튼으로 세션 초기화

## 실행 방법

1. 의존성 설치

   ```
   pip install -r requirements.txt
   ```

2. 앱 실행

   ```
   streamlit run streamlit_app.py
   ```

3. 사이드바에 [OpenAI API 키](https://platform.openai.com/account/api-keys)를 입력하고 시작

## 환경변수로 API 키 설정 (선택)

매번 입력하는 대신 `.streamlit/secrets.toml`에 저장할 수 있습니다.

```toml
OPENAI_API_KEY = "sk-..."
```
