import json
import streamlit as st
from openai import OpenAI

st.title("💬 Chatbot")
st.write(
    "OpenAI API 키를 입력하고 사이드바에서 모델과 파라미터를 설정하세요. "
    "API 키는 [여기](https://platform.openai.com/account/api-keys)에서 발급받을 수 있습니다."
)

# --- Sidebar ---
with st.sidebar:
    st.header("설정")

    openai_api_key = st.text_input("OpenAI API Key", type="password")

    st.divider()

    model = st.selectbox(
        "모델 선택",
        options=[
            "gpt-5.4-mini",
            "gpt-5.4-nano",
            "gpt-5.4",
            "gpt-5.5",
            "gpt-5.5-pro",
            "gpt-4o-mini",
            "gpt-4o",
        ],
        index=0,
        help="gpt-5.4-mini: 성능/가격 균형 (권장) | gpt-5.4-nano: 초저비용/빠름 | gpt-5.4: 고성능 | gpt-5.5: 최신 플래그십 | gpt-5.5-pro: 최고 성능",
    )

    temperature = st.slider(
        "Temperature (창의성)",
        min_value=0.0,
        max_value=2.0,
        value=1.0,
        step=0.1,
        help="낮을수록 일관성 있는 답변, 높을수록 창의적인 답변",
    )

    max_tokens = st.slider(
        "Max Tokens (최대 응답 길이)",
        min_value=256,
        max_value=4096,
        value=1024,
        step=256,
    )

    st.divider()

    st.subheader("채팅 기록 내보내기")

    if "messages" in st.session_state and st.session_state.messages:
        # TXT 내보내기
        txt_lines = []
        for m in st.session_state.messages:
            role = "나" if m["role"] == "user" else "Assistant"
            txt_lines.append(f"[{role}]\n{m['content']}\n")
        txt_data = "\n".join(txt_lines)

        st.download_button(
            label="TXT로 다운로드",
            data=txt_data,
            file_name="chat_history.txt",
            mime="text/plain",
        )

        # JSON 내보내기
        json_data = json.dumps(st.session_state.messages, ensure_ascii=False, indent=2)
        st.download_button(
            label="JSON으로 다운로드",
            data=json_data,
            file_name="chat_history.json",
            mime="application/json",
        )
    else:
        st.caption("대화를 시작하면 내보내기 버튼이 활성화됩니다.")

    if st.button("대화 초기화", type="secondary"):
        st.session_state.messages = []
        st.rerun()

# --- Main chat area ---
if not openai_api_key:
    st.info("사이드바에 OpenAI API 키를 입력하세요.", icon="🗝️")
    st.stop()

client = OpenAI(api_key=openai_api_key)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("메시지를 입력하세요..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )

    with st.chat_message("assistant"):
        response = st.write_stream(stream)
    st.session_state.messages.append({"role": "assistant", "content": response})
