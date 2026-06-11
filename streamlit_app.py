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

st.set_page_config(page_title="✈️ Travel Chatbot", page_icon="✈️", layout="wide")

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

SYSTEM_PROMPT = """You are a friendly and professional travel assistant.
You provide information on travel destinations, attractions, restaurants, accommodations,
transportation, travel costs, local culture, weather, and packing tips.
Always respond in English, use emojis appropriately, and give specific, practical advice."""

SUGGESTIONS = [
    "🏝️ Plan a 4-day itinerary for Jeju Island",
    "💰 How much budget do I need for Europe backpacking?",
    "🌏 Recommend travel destinations in Southeast Asia",
    "🗼 Must-see spots in Tokyo, Japan",
]

DEFAULT_CHECKLIST = {
    "📄 Documents": ["Passport", "Visa", "Flight ticket copy", "Travel insurance", "Hotel reservation"],
    "👕 Clothing": ["Underwear (per day)", "Tops", "Bottoms", "Jacket/Coat", "Swimwear", "Sneakers", "Sandals"],
    "🧴 Toiletries": ["Toothbrush/Toothpaste", "Shampoo", "Sunscreen", "Cosmetics", "Razor", "Wet wipes"],
    "💻 Electronics": ["Phone charger", "Power bank", "Universal adapter", "Earphones", "Camera"],
    "🏥 Medical": ["First-aid kit", "Painkillers", "Band-aids", "Antacids", "Motion sickness pills", "Bug repellent"],
}

WMO_CODES = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
    45: ("Fog", "🌫️"), 48: ("Icy fog", "🌫️"),
    51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"), 55: ("Heavy drizzle", "🌦️"),
    61: ("Light rain", "🌧️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    71: ("Light snow", "🌨️"), 73: ("Snow", "🌨️"), 75: ("Heavy snow", "❄️"),
    80: ("Showers", "🌦️"), 81: ("Heavy showers", "🌦️"), 82: ("Violent showers", "⛈️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm + hail", "⛈️"), 99: ("Thunderstorm + heavy hail", "⛈️"),
}


def geocode(place):
    try:
        res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": place, "format": "json", "limit": 1, "addressdetails": 1},
            headers={"User-Agent": "travel-chatbot/1.0", "Accept-Language": "en"},
            timeout=5,
        )
        data = res.json()
        if data:
            name = data[0].get("display_name", "").split(",")[0]
            return float(data[0]["lat"]), float(data[0]["lon"]), name
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


# ── Sidebar ───────────────────────────────────────────
with st.sidebar:
    st.markdown("## ✈️ Travel Chatbot")
    st.markdown("---")
    openai_api_key = st.text_input("🔑 OpenAI API Key", type="password")
    st.markdown("---")
    model = st.selectbox(
        "🤖 Model",
        ["gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.4", "gpt-5.5", "gpt-5.5-pro", "gpt-4o-mini", "gpt-4o"],
        index=0,
        help="gpt-5.4-mini: Recommended | gpt-5.5: Latest flagship",
    )
    temperature = st.slider("🎨 Creativity (Temperature)", 0.0, 2.0, 1.0, 0.1)
    max_tokens = st.slider("📏 Max Response Length", 256, 4096, 1024, 256)
    st.markdown("---")

    if "messages" in st.session_state and st.session_state.messages:
        user_count = sum(1 for m in st.session_state.messages if m["role"] == "user")
        st.markdown(f"📊 **Stats** — {user_count} messages sent")

    st.markdown("### 💾 Chat History")
    uploaded = st.file_uploader("📂 Load chat (.json)", type="json", label_visibility="collapsed")
    if uploaded:
        try:
            loaded = json.load(uploaded)
            if isinstance(loaded, list):
                st.session_state.messages = loaded
                st.success("Chat history loaded!")
                st.rerun()
        except Exception:
            st.error("Failed to read file.")

    if "messages" in st.session_state and st.session_state.messages:
        txt_lines = [f"[{'Me' if m['role'] == 'user' else 'AI'}]\n{m['content']}\n" for m in st.session_state.messages]
        c1, c2 = st.columns(2)
        c1.download_button("📄 TXT", "\n".join(txt_lines), "travel_chat.txt", "text/plain", use_container_width=True)
        c2.download_button("📋 JSON", json.dumps(st.session_state.messages, ensure_ascii=False, indent=2), "travel_chat.json", "application/json", use_container_width=True)
    else:
        st.caption("Start chatting to enable export.")

    st.markdown("---")
    if st.button("🗑️ Reset All", use_container_width=True, type="secondary"):
        for key in ["messages", "map_pins", "pending_prompt", "checklist", "weather_data", "itinerary"]:
            st.session_state.pop(key, None)
        st.rerun()

# ── Main ──────────────────────────────────────────────
st.title("✈️ Travel Chatbot")
st.caption("From destination recommendations to trip planning — ask me anything!")

if not openai_api_key:
    st.info("👈 Enter your OpenAI API key in the sidebar to get started.", icon="🗝️")
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

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "💬 Chat", "🗺️ Map", "☀️ Weather", "📅 Itinerary", "💰 Budget", "📋 Checklist", "📊 Data Analysis"
])

# ── Tab 1: Chat ───────────────────────────────────────
with tab1:
    if not st.session_state.messages:
        st.markdown("<div style='text-align:center;padding:30px 0 10px;color:#888;font-size:1.1rem;'>🌍 Where would you like to travel?</div>", unsafe_allow_html=True)
        cols = st.columns(2)
        for i, s in enumerate(SUGGESTIONS):
            if cols[i % 2].button(s, use_container_width=True, key=f"sug_{i}"):
                st.session_state.pending_prompt = s
                st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Voice input
    st.markdown("##### 🎙️ Voice Input")
    audio_bytes = audio_recorder(
        text="  Click mic & speak",
        recording_color="#e74c3c",
        neutral_color="#667eea",
        icon_name="microphone",
        icon_size="lg",
    )
    if audio_bytes:
        audio_hash = hashlib.md5(audio_bytes).hexdigest()
        if st.session_state.get("last_audio_hash") != audio_hash:
            st.session_state.last_audio_hash = audio_hash
            with st.spinner("🎙️ Transcribing audio..."):
                try:
                    audio_file = io.BytesIO(audio_bytes)
                    audio_file.name = "recording.wav"
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                    )
                    st.session_state.pending_prompt = transcript.text
                    st.rerun()
                except Exception as e:
                    st.error(f"Transcription failed: {e}")

    st.markdown("---")

    # Image attachment
    st.markdown("##### 🖼️ Attach Image (optional)")
    uploaded_image = st.file_uploader(
        "Upload image",
        type=None,
        label_visibility="collapsed",
        help="Supported: jpg, jpeg, png, webp",
    )
    if uploaded_image:
        ext = uploaded_image.name.split(".")[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            st.warning(f"Unsupported format: .{ext}  |  Supported: jpg, jpeg, png, webp")
            uploaded_image = None
        else:
            st.image(uploaded_image, width=260, caption="Attached image")
            st.caption("⚠️ Image analysis requires gpt-4o or gpt-4o-mini")

    st.markdown("---")

    active_prompt = st.session_state.pending_prompt
    if active_prompt:
        st.session_state.pending_prompt = None

    user_input = st.chat_input("Ask me anything about travel ✈️")
    prompt = active_prompt or user_input

    if prompt:
        if uploaded_image:
            uploaded_image.seek(0)
            img_b64 = base64.b64encode(uploaded_image.read()).decode("utf-8")
            img_type = uploaded_image.type
            user_content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{img_type};base64,{img_b64}"}},
            ]
            st.session_state.messages.append({"role": "user", "content": prompt + " [image attached]"})
        else:
            user_content = prompt
            st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)
            if uploaded_image:
                uploaded_image.seek(0)
                st.image(uploaded_image, width=260)

        history = st.session_state.messages[:-1]
        api_messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + [{"role": m["role"], "content": m["content"]} for m in history]
            + [{"role": "user", "content": user_content}]
        )

        vision_models = ("gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision-preview")
        active_model = model
        if uploaded_image and not model.startswith(tuple(vision_models)):
            active_model = "gpt-4o-mini"
            st.info("🖼️ Switching to **gpt-4o-mini** for image analysis.", icon="ℹ️")

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

# ── Tab 2: Map ────────────────────────────────────────
with tab2:
    st.subheader("🗺️ Destination Map")
    c1, c2, c3 = st.columns([4, 1, 1])
    with c1:
        location_query = st.text_input("Search destination", placeholder="e.g. Paris, Tokyo, New York...", label_visibility="collapsed")
    with c2:
        search_btn = st.button("🔍 Search", type="primary", use_container_width=True)
    with c3:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.map_pins = []
            st.rerun()

    if search_btn and location_query:
        with st.spinner("Searching location..."):
            result = geocode(location_query)
            if result:
                lat, lon, name = result
                if not any(p["name"] == name for p in st.session_state.map_pins):
                    st.session_state.map_pins.append({"lat": lat, "lon": lon, "name": name})
                st.success(f"📍 **{name}** added! (Total: {len(st.session_state.map_pins)})")
            else:
                st.warning("Location not found. Try a different search term.")

    if st.session_state.map_pins:
        st.caption("  ".join([f"📍 {p['name']}" for p in st.session_state.map_pins]))
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

# ── Tab 3: Weather ────────────────────────────────────
with tab3:
    st.subheader("☀️ Destination Weather")
    st.caption("Powered by Open-Meteo — no API key required")

    wc1, wc2 = st.columns([4, 1])
    with wc1:
        weather_city = st.text_input("City", placeholder="e.g. Tokyo, Paris, Bangkok, New York...", label_visibility="collapsed")
    with wc2:
        weather_btn = st.button("Check", type="primary", use_container_width=True)

    if weather_btn and weather_city:
        with st.spinner("Fetching weather..."):
            result = geocode(weather_city)
            if result:
                lat, lon, name = result
                data = fetch_weather(lat, lon)
                if data:
                    st.session_state.weather_data = {"data": data, "name": name}
                else:
                    st.error("Failed to fetch weather data.")
            else:
                st.warning("City not found.")

    if "weather_data" in st.session_state:
        wd = st.session_state.weather_data
        curr = wd["data"]["current"]
        daily = wd["data"]["daily"]
        desc, emoji = WMO_CODES.get(curr["weather_code"], ("Unknown", "❓"))

        st.markdown(f"### {emoji} Current Weather in {wd['name']}")
        cols = st.columns(4)
        cols[0].metric("🌡️ Temperature", f"{curr['temperature_2m']}°C")
        cols[1].metric("🌡️ Feels Like", f"{curr['apparent_temperature']}°C")
        cols[2].metric("💧 Humidity", f"{curr['relative_humidity_2m']}%")
        cols[3].metric("💨 Wind Speed", f"{curr['wind_speed_10m']} km/h")
        st.info(f"Condition: {emoji} {desc}")

        st.markdown("---")
        st.markdown("#### 📅 5-Day Forecast")
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        fcols = st.columns(5)
        for i in range(5):
            _, em = WMO_CODES.get(daily["weather_code"][i], ("", "❓"))
            d = date.fromisoformat(daily["time"][i])
            with fcols[i]:
                st.markdown(f"**{d.month}/{d.day} ({day_names[d.weekday()]})**")
                st.markdown(f"<div style='font-size:2rem;text-align:center'>{em}</div>", unsafe_allow_html=True)
                st.markdown(f"🔴 {daily['temperature_2m_max'][i]}°C")
                st.markdown(f"🔵 {daily['temperature_2m_min'][i]}°C")
                st.markdown(f"🌧️ {daily['precipitation_sum'][i]}mm")

# ── Tab 4: Itinerary ──────────────────────────────────
with tab4:
    st.subheader("📅 Trip Itinerary Planner")

    dc1, dc2 = st.columns(2)
    with dc1:
        start_date = st.date_input("Departure date", value=date.today())
    with dc2:
        end_date = st.date_input("Return date", value=date.today() + timedelta(days=4))

    if start_date > end_date:
        st.warning("Return date cannot be earlier than departure date.")
    else:
        days = (end_date - start_date).days + 1
        st.markdown(f"**Total: {days} days** ({start_date} ~ {end_date})")
        st.markdown("---")

        for i in range(days):
            d = start_date + timedelta(days=i)
            day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()]
            ikey = f"itinerary_{d}"
            if ikey not in st.session_state:
                st.session_state[ikey] = ""
            with st.expander(f"📅 Day {i+1} — {d.month}/{d.day} ({day_name})", expanded=(i == 0)):
                st.text_area(
                    "Schedule",
                    key=ikey,
                    placeholder="e.g.\nMorning: Visit Eiffel Tower\nLunch: Local café\nAfternoon: Louvre Museum",
                    label_visibility="collapsed",
                    height=120,
                )

        itinerary_lines = [f"Trip Itinerary ({start_date} ~ {end_date})\n"]
        for i in range(days):
            d = start_date + timedelta(days=i)
            val = st.session_state.get(f"itinerary_{d}", "")
            if val:
                itinerary_lines.append(f"[Day {i+1} - {d}]\n{val}\n")
        if len(itinerary_lines) > 1:
            st.download_button("📄 Export Itinerary", "\n".join(itinerary_lines), "itinerary.txt", "text/plain")

# ── Tab 5: Budget ─────────────────────────────────────
with tab5:
    st.subheader("💰 Travel Budget Calculator")

    bc1, bc2 = st.columns(2)
    with bc1:
        total_budget = st.number_input("Total Budget ($)", min_value=0, value=2000, step=100, format="%d")
    with bc2:
        trip_days = st.number_input("Trip Duration (days)", min_value=1, value=5, step=1)

    st.markdown("---")
    st.markdown("#### Budget Allocation (%)")

    budget_cats = {"🏨 Accommodation": 30, "🍽️ Food": 25, "✈️ Transport": 20, "🎡 Activities": 15, "🛍️ Shopping/Other": 10}
    pcts = {}
    pcols = st.columns(len(budget_cats))
    for i, (cat, default) in enumerate(budget_cats.items()):
        with pcols[i]:
            pcts[cat] = st.number_input(cat, 0, 100, default, 5, key=f"pct_{cat}")

    total_pct = sum(pcts.values())
    if total_pct != 100:
        st.warning(f"⚠️ Total: {total_pct}% (must equal 100%)")
    else:
        st.success("✅ Total: 100%")

    st.markdown("---")
    st.markdown("#### 📊 Budget Breakdown")
    rows = []
    for cat, pct in pcts.items():
        amt = int(total_budget * pct / 100)
        rows.append({"Category": cat, "Allocation": f"{pct}%", "Total": f"${amt:,}", "Per Day": f"${int(amt/trip_days):,}"})
    st.dataframe(rows, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    c1.metric("💵 Daily Budget", f"${int(total_budget / trip_days):,}")
    c2.metric("💳 Total Budget", f"${total_budget:,}")

# ── Tab 6: Checklist ──────────────────────────────────
with tab6:
    st.subheader("📋 Travel Packing Checklist")

    done_count = sum(1 for v in st.session_state.checklist.values() if v["done"])
    total_count = len(st.session_state.checklist)
    st.progress(done_count / total_count if total_count else 0)
    st.caption(f"Completed: {done_count} / {total_count} items")
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
    st.markdown("#### ➕ Add Item")
    a1, a2, a3 = st.columns([2, 2, 1])
    with a1:
        new_item = st.text_input("Item name", placeholder="e.g. Travel umbrella", label_visibility="collapsed")
    with a2:
        new_cat = st.selectbox("Category", list(cats_map.keys()), label_visibility="collapsed")
    with a3:
        if st.button("➕ Add", use_container_width=True) and new_item:
            k = f"{new_cat}||{new_item}"
            st.session_state.checklist[k] = {"label": new_item, "category": new_cat, "done": False}
            st.rerun()

    if st.button("🔄 Reset Checklist", type="secondary"):
        for k in st.session_state.checklist:
            st.session_state.checklist[k]["done"] = False
            st.session_state.pop(f"chk_{k}", None)
        st.rerun()

# ── Tab 7: Data Analysis ──────────────────────────────
with tab7:
    st.subheader("📊 Data Analysis")
    st.caption("Upload a CSV, Excel, or JSON file for automatic analysis.")

    data_file = st.file_uploader(
        "Upload file (CSV / Excel / JSON)",
        type=None,
        label_visibility="collapsed",
        help="Supported: .csv, .xlsx, .xls, .json",
    )

    if data_file:
        ext = data_file.name.split(".")[-1].lower()
        if ext not in ("csv", "xlsx", "xls", "json"):
            st.error(f"Unsupported format: .{ext}  |  Supported: csv, xlsx, xls, json")
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
            st.error(f"Failed to read file: {e}")
            st.stop()

    if "analysis_df" in st.session_state:
        df = st.session_state.analysis_df

        st.markdown("### 📋 Data Preview")
        ic1, ic2, ic3 = st.columns(3)
        ic1.metric("Rows", f"{df.shape[0]:,}")
        ic2.metric("Columns", f"{df.shape[1]:,}")
        ic3.metric("Missing Values", f"{df.isnull().sum().sum():,}")

        st.dataframe(df.head(20), use_container_width=True)

        with st.expander("📈 Basic Statistics"):
            st.dataframe(df.describe(include="all"), use_container_width=True)

        with st.expander("🔎 Column Info"):
            col_info = pd.DataFrame({
                "Column": df.columns,
                "Type": df.dtypes.values,
                "Missing": df.isnull().sum().values,
                "Unique Values": [df[c].nunique() for c in df.columns],
            })
            st.dataframe(col_info, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### 📊 Chart Visualization")

        num_cols = df.select_dtypes(include="number").columns.tolist()
        all_cols = df.columns.tolist()

        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            chart_type = st.selectbox("Chart Type", ["Bar Chart", "Line Chart", "Scatter Plot", "Histogram", "Pie Chart"])
        with cc2:
            x_col = st.selectbox("X Axis", all_cols)
        with cc3:
            if chart_type in ("Bar Chart", "Line Chart", "Scatter Plot"):
                y_col = st.selectbox("Y Axis", num_cols if num_cols else all_cols)
            else:
                y_col = None

        try:
            if chart_type == "Bar Chart":
                fig = px.bar(df, x=x_col, y=y_col, title=f"{x_col} vs {y_col}")
            elif chart_type == "Line Chart":
                fig = px.line(df, x=x_col, y=y_col, title=f"{x_col} vs {y_col}")
            elif chart_type == "Scatter Plot":
                fig = px.scatter(df, x=x_col, y=y_col, title=f"{x_col} vs {y_col}")
            elif chart_type == "Histogram":
                fig = px.histogram(df, x=x_col, title=f"Distribution of {x_col}")
            elif chart_type == "Pie Chart":
                vc = df[x_col].value_counts().reset_index()
                vc.columns = [x_col, "count"]
                fig = px.pie(vc, names=x_col, values="count", title=f"{x_col} Distribution")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"Chart error: {e}")

        st.markdown("---")
        st.markdown("### 🤖 AI Data Insights")
        st.caption("Let AI read your data and provide key insights.")

        if st.button("✨ Analyze with AI", type="primary"):
            with st.spinner("AI is analyzing your data..."):
                sample = df.head(30).to_string()
                stats = df.describe(include="all").to_string()
                analysis_prompt = f"""Please analyze the following dataset.

[Data Sample (top 30 rows)]
{sample}

[Basic Statistics]
{stats}

Please provide:
1. Data overview (what kind of data is this?)
2. 3-5 key insights
3. Outliers or notable observations
4. Recommended next steps for further analysis"""

                stream = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a data analysis expert. Analyze the given data clearly and practically."},
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
            "<p>Upload a CSV, Excel (.xlsx), or JSON file to get started</p>"
            "</div>",
            unsafe_allow_html=True,
        )
