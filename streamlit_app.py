import io
import base64
import hashlib
import json
import requests
import folium
import pandas as pd
import plotly.express as px
from streamlit_folium import st_folium
from audio_recorder_streamlit import audio_recorder
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

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["💬 채팅", "🗺️ 지도", "☀️ 날씨", "📅 일정", "💰 예산", "📋 체크리스트", "📊 데이터 분석"])

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

    # 음성 입력
    st.markdown("##### 🎙️ 음성으로 질문하기")
    audio_bytes = audio_recorder(
        text="  마이크 클릭 후 말씀하세요",
        recording_color="#e74c3c",
        neutral_color="#667eea",
        icon_name="microphone",
        icon_size="lg",
    )
    if audio_bytes:
        audio_hash = hashlib.md5(audio_bytes).hexdigest()
        if st.session_state.get("last_audio_hash") != audio_hash:
            st.session_state.last_audio_hash = audio_hash
            with st.spinner("🎙️ 음성을 텍스트로 변환 중..."):
                try:
                    audio_file = io.BytesIO(audio_bytes)
                    audio_file.name = "recording.wav"
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="ko",
                    )
                    st.session_state.pending_prompt = transcript.text
                    st.rerun()
                except Exception as e:
                    st.error(f"음성 인식 실패: {e}")

    st.markdown("---")

    # 이미지 첨부
    st.markdown("##### 🖼️ 이미지 첨부 (선택)")
    uploaded_image = st.file_uploader(
        "이미지 업로드",
        type=None,
        label_visibility="collapsed",
        help="지원 형식: jpg, jpeg, png, webp",
    )
    if uploaded_image:
        ext = uploaded_image.name.split(".")[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            st.warning(f"지원하지 않는 형식입니다: .{ext}  |  지원: jpg, jpeg, png, webp")
            uploaded_image = None
        else:
            st.image(uploaded_image, width=260, caption="첨부된 이미지")
            st.caption("⚠️ gpt-4o / gpt-4o-mini 이상 모델에서만 이미지 분석 가능")

    st.markdown("---")

    active_prompt = st.session_state.pending_prompt
    if active_prompt:
        st.session_state.pending_prompt = None

    user_input = st.chat_input("여행에 대해 무엇이든 물어보세요 ✈️")
    prompt = active_prompt or user_input

    if prompt:
        # 이미지가 첨부된 경우 vision 형식으로 메시지 구성
        if uploaded_image:
            uploaded_image.seek(0)
            img_b64 = base64.b64encode(uploaded_image.read()).decode("utf-8")
            img_type = uploaded_image.type
            user_content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{img_type};base64,{img_b64}"}},
            ]
            # 히스토리엔 텍스트만 저장 (base64는 용량이 크므로)
            st.session_state.messages.append({"role": "user", "content": prompt + " [이미지 첨부]"})
        else:
            user_content = prompt
            st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)
            if uploaded_image:
                uploaded_image.seek(0)
                st.image(uploaded_image, width=260)

        # API 전송용 메시지 (마지막 메시지만 vision 형식 적용)
        history = st.session_state.messages[:-1]
        api_messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + [{"role": m["role"], "content": m["content"]} for m in history]
            + [{"role": "user", "content": user_content}]
        )

        # 이미지 첨부 시 Vision 지원 모델로 자동 전환
        vision_models = ("gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision-preview")
        active_model = model
        if uploaded_image and not model.startswith(tuple(vision_models)):
            active_model = "gpt-4o-mini"
            st.info("🖼️ 이미지 분석을 위해 **gpt-4o-mini** 모델로 자동 전환됩니다.", icon="ℹ️")

        stream = client.chat.completions.create(
            model=active_model,
            messages=api_messages,
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

# ── 탭 7: 데이터 분석 ─────────────────────────────────
with tab7:
    st.subheader("📊 데이터 분석")
    st.caption("CSV, Excel, JSON 파일을 업로드하면 자동으로 분석해드립니다.")

    data_file = st.file_uploader(
        "파일 업로드 (CSV / Excel / JSON)",
        type=None,
        label_visibility="collapsed",
        help="지원 형식: .csv, .xlsx, .xls, .json",
    )

    if data_file:
        ext = data_file.name.split(".")[-1].lower()
        if ext not in ("csv", "xlsx", "xls", "json"):
            st.error(f"지원하지 않는 형식입니다: .{ext}  |  지원: csv, xlsx, xls, json")
            st.stop()
        try:
            if ext == "csv":
                df = pd.read_csv(data_file)
            elif ext in ("xlsx", "xls"):
                df = pd.read_excel(io.BytesIO(data_file.read()))
            elif ext == "json":
                df = pd.read_json(data_file)
            st.session_state.analysis_df = df
        except Exception as e:
            st.error(f"파일 읽기 실패: {e}")
            st.stop()

    if "analysis_df" in st.session_state:
        df = st.session_state.analysis_df

        # 기본 정보
        st.markdown("### 📋 데이터 미리보기")
        ic1, ic2, ic3 = st.columns(3)
        ic1.metric("행 수", f"{df.shape[0]:,}")
        ic2.metric("열 수", f"{df.shape[1]:,}")
        ic3.metric("결측값", f"{df.isnull().sum().sum():,}")

        st.dataframe(df.head(20), use_container_width=True)

        # 기본 통계
        with st.expander("📈 기본 통계 (describe)"):
            st.dataframe(df.describe(include="all"), use_container_width=True)

        # 컬럼 정보
        with st.expander("🔎 컬럼 정보"):
            col_info = pd.DataFrame({
                "컬럼명": df.columns,
                "타입": df.dtypes.values,
                "결측값": df.isnull().sum().values,
                "고유값 수": [df[c].nunique() for c in df.columns],
            })
            st.dataframe(col_info, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### 📊 차트 시각화")

        num_cols = df.select_dtypes(include="number").columns.tolist()
        all_cols = df.columns.tolist()

        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            chart_type = st.selectbox("차트 종류", ["막대그래프", "선 그래프", "산점도", "히스토그램", "파이차트"])
        with cc2:
            x_col = st.selectbox("X축", all_cols)
        with cc3:
            if chart_type in ("막대그래프", "선 그래프", "산점도"):
                y_col = st.selectbox("Y축", num_cols if num_cols else all_cols)
            else:
                y_col = None

        try:
            if chart_type == "막대그래프":
                fig = px.bar(df, x=x_col, y=y_col, title=f"{x_col} vs {y_col}")
            elif chart_type == "선 그래프":
                fig = px.line(df, x=x_col, y=y_col, title=f"{x_col} vs {y_col}")
            elif chart_type == "산점도":
                fig = px.scatter(df, x=x_col, y=y_col, title=f"{x_col} vs {y_col}")
            elif chart_type == "히스토그램":
                fig = px.histogram(df, x=x_col, title=f"{x_col} 분포")
            elif chart_type == "파이차트":
                vc = df[x_col].value_counts().reset_index()
                vc.columns = [x_col, "count"]
                fig = px.pie(vc, names=x_col, values="count", title=f"{x_col} 비율")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"차트 생성 실패: {e}")

        st.markdown("---")
        st.markdown("### 🤖 AI 데이터 인사이트")
        st.caption("AI가 데이터를 읽고 주요 인사이트와 특이점을 분석해드립니다.")

        if st.button("✨ AI 분석 요청", type="primary"):
            with st.spinner("AI가 데이터를 분석 중입니다..."):
                sample = df.head(30).to_string()
                stats = df.describe(include="all").to_string()
                analysis_prompt = f"""다음 데이터를 분석해주세요.

[데이터 샘플 (상위 30행)]
{sample}

[기본 통계]
{stats}

다음 내용을 한국어로 분석해주세요:
1. 데이터 개요 (어떤 데이터인지)
2. 주요 인사이트 3~5가지
3. 특이값 또는 주목할 점
4. 추가 분석 추천사항"""

                stream = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "당신은 데이터 분석 전문가입니다. 주어진 데이터를 명확하고 실용적으로 분석해주세요."},
                        {"role": "user", "content": analysis_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=1500,
                    stream=True,
                )
                with st.chat_message("assistant"):
                    st.write_stream(stream)
    else:
        st.markdown(
            "<div style='text-align:center;padding:60px 0;color:#888;'>"
            "<div style='font-size:3rem;'>📂</div>"
            "<p>CSV, Excel(.xlsx), JSON 파일을 업로드하세요</p>"
            "</div>",
            unsafe_allow_html=True,
        )
