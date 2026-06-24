"""Taichu 前端 - Streamlit 单页面。"""

import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000/api"

st.set_page_config(page_title="Taichu 太初", page_icon="📖", layout="wide")
st.title("📖 Taichu 太初 — 玄幻小说写作助手")

# ---- Sidebar ----
with st.sidebar:
    st.header("设置")

    try:
        resp = requests.get(f"{API_BASE}/agents", timeout=3)
        agents = resp.json()["agents"] if resp.ok else []
    except Exception:
        agents = []

    agent_names = [a["name"] for a in agents]
    agent_labels = {a["name"]: f"{a['label']} — {a['description']}" for a in agents}

    if agent_names:
        selected_agent = st.selectbox(
            "选择功能模块",
            options=agent_names,
            format_func=lambda x: agent_labels[x],
        )
    else:
        selected_agent = "chat"
        st.warning("无法连接到后端服务")

    st.divider()
    st.caption("太初 v0.1")

# ---- Chat History ----
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ---- Input ----
if prompt := st.chat_input("输入你的写作相关话题..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("太初思考中..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/chat",
                    json={"agent": selected_agent, "message": prompt},
                    timeout=60,
                )
                if resp.ok:
                    reply = resp.json()["response"]
                else:
                    reply = f"错误：{resp.status_code} - {resp.text}"
            except requests.ConnectionError:
                reply = "无法连接到后端，请确认 FastAPI 服务已启动 (uv run uvicorn src.taichu.main:app --reload)"
            except Exception as e:
                reply = f"请求失败：{e}"

        st.write(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
