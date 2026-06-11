import json
import requests
import folium
from streamlit_folium import st_folium
import streamlit as st
from openai import OpenAI

st.set_page_config(
    page_title="✈️ 여행 챗봇",
    page_icon="✈️",
    layout="wide",
)

st.markdown("""
<style>
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f2027, #203a43, #2c5364);
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] p {
    color: #e0e0e0 !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #ffffff !important;
}
[data-testid="stChatMessage"] {
    border-radius: 16px;
    padding: 4px 8px;
}
.stButton > button {
    border-radius: 24px;
    font-weight: 600;
    transition: all 0.2s ease;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
[data-testid="stTextInput"] input {
    border-radius: 12px;
}
h1 {
    background: linear-gradient(90deg, #667eea, #764ba2);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.2rem !important;
}
[data-testid="stTabs"] [role="tab"] {
    font-size: 1rem;
    font-weight: 600;
    padding: 8px 20px;
}
/* 추천 질문 버튼 */
.suggestion-btn > button {
    background: linear-gradient(135deg, #667eea22, #764ba222);
    border: 1px solid #667eea55;
    color: inherit;
    text-align: left;
    font-size: 0.9rem;
}
</style>
""", unsafe_allow_html=True)

SYSTEM_PROMPT = """당신은 친절하고 전문적인 여행 어시스턴트입니다.
여행지 추천, 관광 명소, 맛집, 숙소, 교통편, 여행 비용, 현지 문화와 예절, 날씨, 짐 싸기 팁 등 여행에 관한 모든 정보를 제공합니다.
항상 한국어로 대화하고, 이모지를 적절히 활용해 읽기 쉽고 친근하게 답변하세요.
구체적이고 실용적인 정보를 제공하고, 여행자의 예산과 상황에 맞는 맞춤형 조언을 드리세요."""

SUGGESTIONS = [
    "🏝️ 제주도 3박 4일 추천 일정 짜줘",
    "💰 유럽 배낭여행 예산은 얼마나 필요해?",
    "🌏 동남아 여행지 추천해줘",
    "🗼 일본 도쿄 필수 관광 코스 알려줘",
]

# ── 사이드바 ──────────────────────────────────────────
with st.sidebar:
    st.markdown("## ✈️ 여행 챗봇")
    st.markdown("---")

    openai_api_key = st.text_input("🔑 OpenAI API Key", type="password")

    st.markdown("---")

    model = st.selectbox(
        "🤖 모델",
        options=["gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.4", "gpt-5.5", "gpt-5.5-pro", "gpt-4o-mini", "gpt-4o"],
        index=0,
        help="gpt-5.4-mini: 권장 | gpt-5.5: 최신 플래그십 | gpt-5.5-pro: 최고 성능",
    )

    temperature = st.slider("🎨 창의성 (Temperature)", 0.0, 2.0, 1.0, 0.1)
    max_tokens = st.slider("📏 최대 응답 길이", 256, 4096, 1024, 256)

    st.markdown("---")

    # 대화 통계
    if "messages" in st.session_state and st.session_state.messages:
        user_count = sum(1 for m in st.session_state.messages if m["role"] == "user")
        st.markdown(f"📊 **대화 통계** — {user_count}번 질문")

    st.markdown("### 💾 기록 관리")

    # 불러오기
    uploaded = st.file_uploader("📂 대화 불러오기 (.json)", type="json", label_visibility="collapsed")
    if uploaded:
        try:
            loaded = json.load(uploaded)
            if isinstance(loaded, list):
                st.session_state.messages = loaded
                st.success("대화를 불러왔습니다!")
                st.rerun()
        except Exception:
            st.error("파일을 읽을 수 없습니다.")

    # 내보내기
    if "messages" in st.session_state and st.session_state.messages:
        txt_lines = []
        for m in st.session_state.messages:
            role = "나" if m["role"] == "user" else "AI"
            txt_lines.append(f"[{role}]\n{m['content']}\n")

        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📄 TXT", "\n".join(txt_lines), "travel_chat.txt", "text/plain", use_container_width=True)
        with col2:
            st.download_button("📋 JSON", json.dumps(st.session_state.messages, ensure_ascii=False, indent=2), "travel_chat.json", "application/json", use_container_width=True)
    else:
        st.caption("대화를 시작하면 내보내기가 활성화됩니다.")

    st.markdown("---")

    if st.button("🗑️ 대화 초기화", use_container_width=True, type="secondary"):
        st.session_state.messages = []
        st.session_state.pop("map_pins", None)
        st.rerun()

# ── 메인 ─────────────────────────────────────────────
st.title("✈️ 여행 챗봇")
st.caption("여행지 추천부터 일정 계획까지, 무엇이든 물어보세요!")

if not openai_api_key:
    st.info("👈 사이드바에 OpenAI API 키를 입력하면 시작됩니다.", icon="🗝️")
    st.stop()

client = OpenAI(api_key=openai_api_key)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "map_pins" not in st.session_state:
    st.session_state.map_pins = []
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None

chat_tab, map_tab = st.tabs(["💬 채팅", "🗺️ 지도"])

# ── 채팅 탭 ───────────────────────────────────────────
with chat_tab:
    # 빈 화면: 추천 질문 버튼
    if not st.session_state.messages:
        st.markdown(
            "<div style='text-align:center; padding:30px 0 10px; color:#888; font-size:1.1rem;'>🌍 어디로 여행을 떠나고 싶으신가요?</div>",
            unsafe_allow_html=True,
        )
        cols = st.columns(2)
        for i, s in enumerate(SUGGESTIONS):
            with cols[i % 2]:
                if st.button(s, use_container_width=True, key=f"sug_{i}"):
                    st.session_state.pending_prompt = s
                    st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 추천 질문 버튼 클릭 처리
    active_prompt = st.session_state.pending_prompt
    if active_prompt:
        st.session_state.pending_prompt = None

    user_input = st.chat_input("여행에 대해 무엇이든 물어보세요 ✈️")
    prompt = active_prompt or user_input

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        messages_to_send = [{"role": "system", "content": SYSTEM_PROMPT}] + st.session_state.messages

        stream = client.chat.completions.create(
            model=model,
            messages=messages_to_send,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        with st.chat_message("assistant"):
            response = st.write_stream(stream)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()

# ── 지도 탭 ───────────────────────────────────────────
with map_tab:
    st.subheader("🗺️ 여행지 지도 검색")

    col_input, col_btn, col_clear = st.columns([4, 1, 1])
    with col_input:
        location_query = st.text_input("목적지 검색", placeholder="예: 파리, 제주도, 도쿄...", label_visibility="collapsed")
    with col_btn:
        search_btn = st.button("🔍 검색", type="primary", use_container_width=True)
    with col_clear:
        if st.button("🗑️ 초기화", use_container_width=True):
            st.session_state.map_pins = []
            st.rerun()

    if search_btn and location_query:
        with st.spinner("위치를 검색 중..."):
            try:
                res = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": location_query, "format": "json", "limit": 1},
                    headers={"User-Agent": "travel-chatbot/1.0"},
                    timeout=5,
                )
                results = res.json()
                if results:
                    lat = float(results[0]["lat"])
                    lon = float(results[0]["lon"])
                    name = results[0]["display_name"].split(",")[0]
                    # 중복 제거 후 핀 추가
                    if not any(p["name"] == name for p in st.session_state.map_pins):
                        st.session_state.map_pins.append({"lat": lat, "lon": lon, "name": name})
                    st.success(f"📍 **{name}** 추가됨! (총 {len(st.session_state.map_pins)}개)")
                else:
                    st.warning("위치를 찾을 수 없습니다.")
            except Exception:
                st.error("검색 중 오류가 발생했습니다.")

    # 저장된 핀 목록 표시
    if st.session_state.map_pins:
        pin_names = "　".join([f"📍 {p['name']}" for p in st.session_state.map_pins])
        st.caption(pin_names)

    # 지도 생성
    if st.session_state.map_pins:
        center_lat = sum(p["lat"] for p in st.session_state.map_pins) / len(st.session_state.map_pins)
        center_lon = sum(p["lon"] for p in st.session_state.map_pins) / len(st.session_state.map_pins)
        zoom = 5 if len(st.session_state.map_pins) > 1 else 12
    else:
        center_lat, center_lon, zoom = 36.5, 127.5, 6

    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, tiles="CartoDB positron")

    colors = ["red", "blue", "green", "purple", "orange", "darkred", "darkblue", "darkgreen"]
    for i, pin in enumerate(st.session_state.map_pins):
        folium.Marker(
            location=[pin["lat"], pin["lon"]],
            popup=folium.Popup(f"<b>📍 {pin['name']}</b>", max_width=200),
            tooltip=pin["name"],
            icon=folium.Icon(color=colors[i % len(colors)], icon="star"),
        ).add_to(m)

    st_folium(m, use_container_width=True, height=520)
