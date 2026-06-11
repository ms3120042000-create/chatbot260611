import json
import requests
import folium
from streamlit_folium import st_folium
import streamlit as st
from openai import OpenAI
from datetime import date, timedelta

st.set_page_config(page_title="✈️ 여행 챗봇", page_icon="✈️", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f2027, #203a43, #2c5364);
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] p { color: #e0e0e0 !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #ffffff !important; }
[data-testid="stChatMessage"] { border-radius: 16px; padding: 4px 8px; }
.stButton > button {
    border-radius: 24px; font-weight: 600; transition: all 0.2s ease;
}
.stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
h1 {
    background: linear-gradient(90deg, #667eea, #764ba2);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.2rem !important;
}
[data-testid="stTabs"] [role="tab"] { font-size: 0.95rem; font-weight: 600; padding: 8px 16px; }
</style>
""", unsafe_allow_html=True)

SYSTEM_PROMPT = """당신은 친절하고 전문적인 여행 어시스턴트입니다.
여행지 추천, 관광 명소, 맛집, 숙소, 교통편, 여행 비용, 현지 문화와 예절, 날씨, 짐 싸기 팁 등
여행에 관한 모든 정보를 제공합니다. 항상 한국어로 대화하고, 이모지를 적절히 활용해
읽기 쉽고 친근하게 답변하세요. 구체적이고 실용적인 정보를 제공해주세요."""

SUGGESTIONS = [
    "🏝️ 제주도 3박 4일 추천 일정 짜줘",
    "💰 유럽 배낭여행 예산은 얼마나 필요해?",
    "🌏 동남아 여행지 추천해줘",
    "🗼 일본 도쿄 필수 관광 코스 알려줘",
]

DEFAULT_CHECKLIST = {
    "📄 여권/서류": ["여권", "비자", "항공권 사본", "여행자 보험증", "숙소 예약 확인서"],
    "👕 의류": ["속옷 (일수만큼)", "상의", "하의", "겉옷/재킷", "수영복", "운동화", "편한 슬리퍼"],
    "🧴 세면도구": ["칫솔/치약", "샴푸", "선크림", "화장품", "면도기", "물티슈"],
    "💻 전자기기": ["스마트폰 충전기", "보조배터리", "멀티 어댑터", "이어폰", "카메라"],
    "🏥 비상용품": ["상비약", "진통제", "밴드", "소화제", "멀미약", "모기 기피제"],
}

WMO_CODES = {
    0: ("맑음", "☀️"), 1: ("대체로 맑음", "🌤️"), 2: ("부분 흐림", "⛅"), 3: ("흐림", "☁️"),
    45: ("안개", "🌫️"), 48: ("착빙 안개", "🌫️"),
    51: ("약한 이슬비", "🌦️"), 53: ("이슬비", "🌦️"), 55: ("강한 이슬비", "🌦️"),
    61: ("약한 비", "🌧️"), 63: ("비", "🌧️"), 65: ("강한 비", "🌧️"),
    71: ("약한 눈", "🌨️"), 73: ("눈", "🌨️"), 75: ("강한 눈", "❄️"),
    80: ("소나기", "🌦️"), 81: ("강한 소나기", "🌦️"), 82: ("폭우", "⛈️"),
    95: ("뇌우", "⛈️"), 96: ("뇌우+우박", "⛈️"), 99: ("뇌우+강한 우박", "⛈️"),
}


def geocode(place):
    try:
        res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": place, "format": "json", "limit": 1},
            headers={"User-Agent": "travel-chatbot/1.0"},
            timeout=5,
        )
        data = res.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"].split(",")[0]
    except Exception:
        pass
    return None


def fetch_weather(lat, lon):
    try:
        res = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                "timezone": "auto", "forecast_days": 5,
            },
            timeout=5,
        )
        return res.json()
    except Exception:
        return None


# ── 사이드바 ──────────────────────────────────────────
with st.sidebar:
    st.markdown("## ✈️ 여행 챗봇")
    st.markdown("---")
    openai_api_key = st.text_input("🔑 OpenAI API Key", type="password")
    st.markdown("---")
    model = st.selectbox(
        "🤖 모델",
        ["gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.4", "gpt-5.5", "gpt-5.5-pro", "gpt-4o-mini", "gpt-4o"],
        index=0,
        help="gpt-5.4-mini: 권장 | gpt-5.5: 최신 플래그십",
    )
    temperature = st.slider("🎨 창의성", 0.0, 2.0, 1.0, 0.1)
    max_tokens = st.slider("📏 최대 응답 길이", 256, 4096, 1024, 256)
    st.markdown("---")

    if "messages" in st.session_state and st.session_state.messages:
        user_count = sum(1 for m in st.session_state.messages if m["role"] == "user")
        st.markdown(f"📊 **대화 통계** — {user_count}번 질문")

    st.markdown("### 💾 기록 관리")
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

    if "messages" in st.session_state and st.session_state.messages:
        txt_lines = [f"[{'나' if m['role'] == 'user' else 'AI'}]\n{m['content']}\n" for m in st.session_state.messages]
        c1, c2 = st.columns(2)
        c1.download_button("📄 TXT", "\n".join(txt_lines), "travel_chat.txt", "text/plain", use_container_width=True)
        c2.download_button("📋 JSON", json.dumps(st.session_state.messages, ensure_ascii=False, indent=2), "travel_chat.json", "application/json", use_container_width=True)
    else:
        st.caption("대화를 시작하면 내보내기가 활성화됩니다.")

    st.markdown("---")
    if st.button("🗑️ 전체 초기화", use_container_width=True, type="secondary"):
        for key in ["messages", "map_pins", "pending_prompt", "checklist", "weather_data", "itinerary"]:
            st.session_state.pop(key, None)
        st.rerun()

# ── 메인 ─────────────────────────────────────────────
st.title("✈️ 여행 챗봇")
st.caption("여행지 추천부터 일정 계획까지, 무엇이든 물어보세요!")

if not openai_api_key:
    st.info("👈 사이드바에 OpenAI API 키를 입력하면 시작됩니다.", icon="🗝️")
    st.stop()

client = OpenAI(api_key=openai_api_key)

for key, default in [("messages", []), ("map_pins", []), ("pending_prompt", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

if "checklist" not in st.session_state:
    items = {}
    for cat, lst in DEFAULT_CHECKLIST.items():
        for item in lst:
            items[f"{cat}||{item}"] = {"label": item, "category": cat, "done": False}
    st.session_state.checklist = items

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["💬 채팅", "🗺️ 지도", "☀️ 날씨", "📅 일정", "💰 예산", "📋 체크리스트"])

# ── 탭 1: 채팅 ────────────────────────────────────────
with tab1:
    if not st.session_state.messages:
        st.markdown("<div style='text-align:center;padding:30px 0 10px;color:#888;font-size:1.1rem;'>🌍 어디로 여행을 떠나고 싶으신가요?</div>", unsafe_allow_html=True)
        cols = st.columns(2)
        for i, s in enumerate(SUGGESTIONS):
            if cols[i % 2].button(s, use_container_width=True, key=f"sug_{i}"):
                st.session_state.pending_prompt = s
                st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    active_prompt = st.session_state.pending_prompt
    if active_prompt:
        st.session_state.pending_prompt = None

    user_input = st.chat_input("여행에 대해 무엇이든 물어보세요 ✈️")
    prompt = active_prompt or user_input

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + st.session_state.messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        with st.chat_message("assistant"):
            response = st.write_stream(stream)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()

# ── 탭 2: 지도 ────────────────────────────────────────
with tab2:
    st.subheader("🗺️ 여행지 지도 검색")
    c1, c2, c3 = st.columns([4, 1, 1])
    with c1:
        location_query = st.text_input("목적지", placeholder="예: 파리, 제주도, 도쿄...", label_visibility="collapsed")
    with c2:
        search_btn = st.button("🔍 검색", type="primary", use_container_width=True)
    with c3:
        if st.button("🗑️ 초기화", use_container_width=True):
            st.session_state.map_pins = []
            st.rerun()

    if search_btn and location_query:
        with st.spinner("위치 검색 중..."):
            result = geocode(location_query)
            if result:
                lat, lon, name = result
                if not any(p["name"] == name for p in st.session_state.map_pins):
                    st.session_state.map_pins.append({"lat": lat, "lon": lon, "name": name})
                st.success(f"📍 **{name}** 추가됨! (총 {len(st.session_state.map_pins)}개)")
            else:
                st.warning("위치를 찾을 수 없습니다.")

    if st.session_state.map_pins:
        st.caption("　".join([f"📍 {p['name']}" for p in st.session_state.map_pins]))
        clat = sum(p["lat"] for p in st.session_state.map_pins) / len(st.session_state.map_pins)
        clon = sum(p["lon"] for p in st.session_state.map_pins) / len(st.session_state.map_pins)
        zoom = 5 if len(st.session_state.map_pins) > 1 else 12
    else:
        clat, clon, zoom = 36.5, 127.5, 6

    m = folium.Map(location=[clat, clon], zoom_start=zoom, tiles="CartoDB positron")
    colors = ["red", "blue", "green", "purple", "orange", "darkred", "darkblue", "darkgreen"]
    for i, pin in enumerate(st.session_state.map_pins):
        folium.Marker(
            [pin["lat"], pin["lon"]],
            popup=folium.Popup(f"<b>📍 {pin['name']}</b>", max_width=200),
            tooltip=pin["name"],
            icon=folium.Icon(color=colors[i % len(colors)], icon="star"),
        ).add_to(m)
    st_folium(m, use_container_width=True, height=520)

# ── 탭 3: 날씨 ────────────────────────────────────────
with tab3:
    st.subheader("☀️ 여행지 날씨 조회")
    st.caption("무료 Open-Meteo API 사용 — 별도 API 키 불필요")

    wc1, wc2 = st.columns([4, 1])
    with wc1:
        weather_city = st.text_input("도시 입력", placeholder="예: 도쿄, 파리, 방콕, 뉴욕...", label_visibility="collapsed")
    with wc2:
        weather_btn = st.button("조회", type="primary", use_container_width=True)

    if weather_btn and weather_city:
        with st.spinner("날씨를 불러오는 중..."):
            result = geocode(weather_city)
            if result:
                lat, lon, name = result
                data = fetch_weather(lat, lon)
                if data:
                    st.session_state.weather_data = {"data": data, "name": name}
                else:
                    st.error("날씨 데이터를 불러올 수 없습니다.")
            else:
                st.warning("도시를 찾을 수 없습니다.")

    if "weather_data" in st.session_state:
        wd = st.session_state.weather_data
        curr = wd["data"]["current"]
        daily = wd["data"]["daily"]
        desc, emoji = WMO_CODES.get(curr["weather_code"], ("알 수 없음", "❓"))

        st.markdown(f"### {emoji} {wd['name']} 현재 날씨")
        cols = st.columns(4)
        cols[0].metric("🌡️ 기온", f"{curr['temperature_2m']}°C")
        cols[1].metric("🌡️ 체감", f"{curr['apparent_temperature']}°C")
        cols[2].metric("💧 습도", f"{curr['relative_humidity_2m']}%")
        cols[3].metric("💨 풍속", f"{curr['wind_speed_10m']} km/h")
        st.info(f"날씨 상태: {emoji} {desc}")

        st.markdown("---")
        st.markdown("#### 📅 5일 예보")
        fcols = st.columns(5)
        for i in range(5):
            _, em = WMO_CODES.get(daily["weather_code"][i], ("", "❓"))
            d = date.fromisoformat(daily["time"][i])
            day_kr = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
            with fcols[i]:
                st.markdown(f"**{d.month}/{d.day}({day_kr})**")
                st.markdown(f"<div style='font-size:2rem;text-align:center'>{em}</div>", unsafe_allow_html=True)
                st.markdown(f"🔴 {daily['temperature_2m_max'][i]}°C")
                st.markdown(f"🔵 {daily['temperature_2m_min'][i]}°C")
                st.markdown(f"🌧️ {daily['precipitation_sum'][i]}mm")

# ── 탭 4: 일정 플래너 ─────────────────────────────────
with tab4:
    st.subheader("📅 여행 일정 플래너")

    dc1, dc2 = st.columns(2)
    with dc1:
        start_date = st.date_input("출발일", value=date.today())
    with dc2:
        end_date = st.date_input("귀국일", value=date.today() + timedelta(days=4))

    if start_date > end_date:
        st.warning("귀국일이 출발일보다 빠릅니다.")
    else:
        days = (end_date - start_date).days + 1
        st.markdown(f"**총 {days}일 일정** ({start_date} ~ {end_date})")
        st.markdown("---")

        for i in range(days):
            d = start_date + timedelta(days=i)
            day_kr = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
            ikey = f"itinerary_{d}"
            if ikey not in st.session_state:
                st.session_state[ikey] = ""
            with st.expander(f"📅 {i+1}일차 — {d.month}/{d.day} ({day_kr})", expanded=(i == 0)):
                st.text_area(
                    "일정",
                    key=ikey,
                    placeholder="예) 오전: 에펠탑 방문\n점심: 현지 카페\n오후: 루브르 박물관",
                    label_visibility="collapsed",
                    height=120,
                )

        itinerary_lines = [f"여행 일정 ({start_date} ~ {end_date})\n"]
        for i in range(days):
            d = start_date + timedelta(days=i)
            val = st.session_state.get(f"itinerary_{d}", "")
            if val:
                itinerary_lines.append(f"[{i+1}일차 - {d}]\n{val}\n")
        if len(itinerary_lines) > 1:
            st.download_button("📄 일정 내보내기", "\n".join(itinerary_lines), "itinerary.txt", "text/plain")

# ── 탭 5: 예산 계산기 ─────────────────────────────────
with tab5:
    st.subheader("💰 여행 예산 계산기")

    bc1, bc2 = st.columns(2)
    with bc1:
        total_budget = st.number_input("총 예산 (원)", min_value=0, value=1_500_000, step=100_000, format="%d")
    with bc2:
        trip_days = st.number_input("여행 일수", min_value=1, value=5, step=1)

    st.markdown("---")
    st.markdown("#### 항목별 비율 설정 (%)")

    budget_cats = {"🏨 숙소": 30, "🍽️ 식비": 25, "✈️ 교통": 20, "🎡 관광/액티비티": 15, "🛍️ 쇼핑/기타": 10}
    pcts = {}
    pcols = st.columns(len(budget_cats))
    for i, (cat, default) in enumerate(budget_cats.items()):
        with pcols[i]:
            pcts[cat] = st.number_input(cat, 0, 100, default, 5, key=f"pct_{cat}")

    total_pct = sum(pcts.values())
    if total_pct != 100:
        st.warning(f"⚠️ 합계: {total_pct}% (100%가 되도록 조정해주세요)")
    else:
        st.success("✅ 합계 100%")

    st.markdown("---")
    st.markdown("#### 📊 예산 상세")
    rows = []
    for cat, pct in pcts.items():
        amt = int(total_budget * pct / 100)
        rows.append({"항목": cat, "비율": f"{pct}%", "총 금액": f"{amt:,}원", "1일 평균": f"{int(amt/trip_days):,}원"})
    st.dataframe(rows, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    c1.metric("💵 1일 총 예산", f"{int(total_budget / trip_days):,}원")
    c2.metric("💳 총 예산", f"{total_budget:,}원")

# ── 탭 6: 체크리스트 ──────────────────────────────────
with tab6:
    st.subheader("📋 여행 준비물 체크리스트")

    done_count = sum(1 for v in st.session_state.checklist.values() if v["done"])
    total_count = len(st.session_state.checklist)
    st.progress(done_count / total_count if total_count else 0)
    st.caption(f"완료: {done_count} / {total_count}개")
    st.markdown("---")

    cats_map = {}
    for k, v in st.session_state.checklist.items():
        cats_map.setdefault(v["category"], []).append(k)

    for cat, keys in cats_map.items():
        cat_done = sum(1 for k in keys if st.session_state.checklist[k]["done"])
        with st.expander(f"{cat}  ({cat_done}/{len(keys)})", expanded=True):
            for k in keys:
                item = st.session_state.checklist[k]
                chk_key = f"chk_{k}"
                if chk_key not in st.session_state:
                    st.session_state[chk_key] = item["done"]
                checked = st.checkbox(item["label"], key=chk_key)
                st.session_state.checklist[k]["done"] = checked

    st.markdown("---")
    st.markdown("#### ➕ 항목 추가")
    a1, a2, a3 = st.columns([2, 2, 1])
    with a1:
        new_item = st.text_input("항목 이름", placeholder="예: 여행용 우산", label_visibility="collapsed")
    with a2:
        new_cat = st.selectbox("카테고리", list(cats_map.keys()), label_visibility="collapsed")
    with a3:
        if st.button("➕ 추가", use_container_width=True) and new_item:
            k = f"{new_cat}||{new_item}"
            st.session_state.checklist[k] = {"label": new_item, "category": new_cat, "done": False}
            st.rerun()

    if st.button("🔄 체크 초기화", type="secondary"):
        for k in st.session_state.checklist:
            st.session_state.checklist[k]["done"] = False
            st.session_state.pop(f"chk_{k}", None)
        st.rerun()
