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
/* 사이드바 */
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

/* 채팅 버블 */
[data-testid="stChatMessage"] {
    border-radius: 16px;
    padding: 4px 8px;
}

/* 버튼 */
.stButton > button {
    border-radius: 24px;
    font-weight: 600;
    transition: all 0.2s ease;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

/* 입력창 */
[data-testid="stTextInput"] input,
[data-testid="stChatInput"] textarea {
    border-radius: 12px;
}

/* 타이틀 */
h1 {
    background: linear-gradient(90deg, #667eea, #764ba2);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.2rem !important;
}

/* 탭 */
[data-testid="stTabs"] [role="tab"] {
    font-size: 1rem;
    font-weight: 600;
    padding: 8px 20px;
}
</style>
""", unsafe_allow_html=True)

SYSTEM_PROMPT = """당신은 친절하고 전문적인 여행 어시스턴트입니다.
여행지 추천, 관광 명소, 맛집, 숙소, 교통편, 여행 비용, 현지 문화와 예절, 날씨, 짐 싸기 팁 등 여행에 관한 모든 정보를 제공합니다.
항상 한국어로 대화하고, 이모지를 적절히 활용해 읽기 쉽고 친근하게 답변하세요.
구체적이고 실용적인 정보를 제공하고, 여행자의 예산과 상황에 맞는 맞춤형 조언을 드리세요."""

# ── 사이드바 ──────────────────────────────────────────
with st.sidebar:
    st.markdown("## ✈️ 여행 챗봇")
    st.markdown("---")

    openai_api_key = st.text_input("🔑 OpenAI API Key", type="password")

    st.markdown("---")

    model = st.selectbox(
        "🤖 모델",
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
        help="gpt-5.4-mini: 권장 | gpt-5.5: 최신 플래그십 | gpt-5.5-pro: 최고 성능",
    )

    temperature = st.slider("🎨 창의성 (Temperature)", 0.0, 2.0, 1.0, 0.1)
    max_tokens = st.slider("📏 최대 응답 길이", 256, 4096, 1024, 256)

    st.markdown("---")

    st.markdown("### 💾 기록 내보내기")
    if "messages" in st.session_state and st.session_state.messages:
        txt_lines = []
        for m in st.session_state.messages:
            role = "나" if m["role"] == "user" else "AI"
            txt_lines.append(f"[{role}]\n{m['content']}\n")

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📄 TXT",
                "\n".join(txt_lines),
                "travel_chat.txt",
                "text/plain",
                use_container_width=True,
            )
        with col2:
            st.download_button(
                "📋 JSON",
                json.dumps(st.session_state.messages, ensure_ascii=False, indent=2),
                "travel_chat.json",
                "application/json",
                use_container_width=True,
            )
    else:
        st.caption("대화를 시작하면 내보내기가 활성화됩니다.")

    st.markdown("---")

    if st.button("🗑️ 대화 초기화", use_container_width=True, type="secondary"):
        st.session_state.messages = []
        st.session_state.pop("map_location", None)
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

chat_tab, map_tab = st.tabs(["💬 채팅", "🗺️ 지도"])

# ── 채팅 탭 ───────────────────────────────────────────
with chat_tab:
    if not st.session_state.messages:
        st.markdown(
            """
            <div style='text-align:center; padding: 40px; color: #888;'>
                <div style='font-size: 3rem;'>🌍</div>
                <p style='font-size: 1.1rem;'>어디로 여행을 떠나고 싶으신가요?<br>목적지, 일정, 예산 등 무엇이든 물어보세요!</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("여행에 대해 무엇이든 물어보세요 ✈️"):
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

# ── 지도 탭 ───────────────────────────────────────────
with map_tab:
    st.subheader("🗺️ 여행지 지도 검색")

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        location_query = st.text_input(
            "목적지 검색",
            placeholder="예: 파리, 제주도, 도쿄, 바르셀로나...",
            label_visibility="collapsed",
        )
    with col_btn:
        search_btn = st.button("🔍 검색", type="primary", use_container_width=True)

    if "map_location" not in st.session_state:
        st.session_state.map_location = {"lat": 36.5, "lon": 127.5, "name": None, "zoom": 6}

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
                    st.session_state.map_location = {"lat": lat, "lon": lon, "name": name, "zoom": 12}
                    st.success(f"📍 **{name}** 을(를) 찾았습니다!")
                else:
                    st.warning("위치를 찾을 수 없습니다. 다른 검색어를 시도해보세요.")
            except Exception:
                st.error("지도 검색 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

    loc = st.session_state.map_location
    m = folium.Map(location=[loc["lat"], loc["lon"]], zoom_start=loc["zoom"], tiles="CartoDB positron")

    if loc["name"]:
        folium.Marker(
            location=[loc["lat"], loc["lon"]],
            popup=folium.Popup(f"<b>📍 {loc['name']}</b>", max_width=200),
            tooltip=loc["name"],
            icon=folium.Icon(color="red", icon="star"),
        ).add_to(m)

    st_folium(m, use_container_width=True, height=520)
