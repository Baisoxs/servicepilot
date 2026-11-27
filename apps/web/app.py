"""ServicePilot 最小聊天页（W4 v0.1）。

前端只做三件事：收集输入、调 FastAPI、展示结果。
登录态、会话、消息全部由后端负责。
"""

import contextlib
import json
import os

import httpx
import streamlit as st

# 本机跑默认连 127.0.0.1:8000；以后把前端丢进容器，用环境变量改成服务名
API_URL = os.environ.get("SERVICEPILOT_API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="ServicePilot", page_icon="🛠️", layout="wide")


# ---------- 基础设施 ----------


@st.cache_resource
def get_client() -> httpx.Client:
    """整个应用共用一个 HTTP 客户端（带连接池）。"""
    return httpx.Client(base_url=API_URL, timeout=60)


def api(method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
    """统一带上 Authorization 头，并把 HTTP 错误抛出来。"""
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = get_client().request(method, path, headers=headers, **kwargs)
    resp.raise_for_status()
    return resp


def read_error(exc: httpx.HTTPStatusError) -> str:
    """从统一错误体里取出给人看的 message。"""
    try:
        body = exc.response.json()
    except ValueError:
        return f"请求失败：HTTP {exc.response.status_code}"
    return body.get("message") or body.get("detail") or f"请求失败：HTTP {exc.response.status_code}"


def back_to_login_if_expired(exc: httpx.HTTPStatusError) -> None:
    """access token 只有 15 分钟，过期就清掉登录态回登录页。"""
    if exc.response.status_code == 401:
        st.session_state.clear()
        st.rerun()


def init_state() -> None:
    defaults = {
        "token": None,
        "email": None,
        "conversations": [],
        "current_conv": None,
        "messages": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ---------- 数据操作 ----------


def load_conversations() -> None:
    resp = api(
        "GET",
        "/v1/conversations",
        token=st.session_state.token,
        params={"limit": 100},
    )
    st.session_state.conversations = resp.json()["items"]


def load_messages(conversation_id: str) -> None:
    resp = api(
        "GET",
        f"/v1/conversations/{conversation_id}/messages",
        token=st.session_state.token,
        params={"limit": 100},
    )
    st.session_state.messages = resp.json()["items"]


def new_conversation() -> None:
    resp = api(
        "POST",
        "/v1/conversations",
        token=st.session_state.token,
        json={"title": "新会话"},
    )
    conv = resp.json()
    load_conversations()
    st.session_state.current_conv = conv["id"]
    st.session_state.messages = []


def stream_chat(conversation_id: str, message: str):
    """把后端 SSE 拆成一个个 delta，喂给 st.write_stream。"""
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    payload = {"conversation_id": conversation_id, "message": message}

    with get_client().stream("POST", "/v1/chat", json=payload, headers=headers) as resp:
        if resp.is_error:
            # 流式响应的 body 默认不读；不先 read 的话，raise_for_status 之后
            # read_error() 拿不到后端返回的错误 JSON，只会抛出 ResponseNotRead。
            resp.read()
            resp.raise_for_status()

        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue

            data = line.removeprefix("data: ")
            if data == "[DONE]":
                break

            event = json.loads(data)
            if "error" in event:
                raise RuntimeError(event["error"])
            yield event["delta"]


# ---------- 页面 ----------


def show_login() -> None:
    st.title("🛠️ ServicePilot")
    st.caption("登录后用邮箱和密码开始对话")

    login_tab, register_tab = st.tabs(["登录", "注册"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("邮箱", key="login_email")
            password = st.text_input("密码", type="password", key="login_password")
            submitted = st.form_submit_button("登录")

        if submitted:
            try:
                resp = api(
                    "POST",
                    "/v1/auth/login",
                    json={"email": email, "password": password},
                )
                st.session_state.token = resp.json()["access_token"]
                st.session_state.email = email
                load_conversations()
                st.rerun()
            except httpx.HTTPStatusError as exc:
                st.error(read_error(exc))
            except httpx.HTTPError:
                st.error("连不上后端，确认 API 已经启动")

    with register_tab:
        with st.form("register_form"):
            email = st.text_input("邮箱", key="register_email")
            password = st.text_input("密码（至少 8 位）", type="password", key="register_password")
            submitted = st.form_submit_button("注册")

        if submitted:
            try:
                api(
                    "POST",
                    "/v1/auth/register",
                    json={"email": email, "password": password},
                )
                st.success("注册成功，请到「登录」页登录")
            except httpx.HTTPStatusError as exc:
                st.error(read_error(exc))
            except httpx.HTTPError:
                st.error("连不上后端，确认 API 已经启动")


def show_chat() -> None:
    with st.sidebar:
        st.caption(f"当前用户：{st.session_state.email}")

        if st.button("＋ 新建会话"):
            try:
                new_conversation()
                st.rerun()
            except httpx.HTTPStatusError as exc:
                back_to_login_if_expired(exc)
                st.error(read_error(exc))
            except httpx.HTTPError:
                st.error("连不上后端")

        st.divider()

        for conv in st.session_state.conversations:
            if st.button(conv["title"] or "未命名", key=f"conv-{conv['id']}"):
                st.session_state.current_conv = conv["id"]
                try:
                    load_messages(conv["id"])
                    st.rerun()
                except httpx.HTTPStatusError as exc:
                    back_to_login_if_expired(exc)
                    st.error(read_error(exc))
                except httpx.HTTPError:
                    st.error("连不上后端")

        st.divider()
        if st.button("退出登录"):
            st.session_state.clear()
            st.rerun()

    st.title("🛠️ ServicePilot")

    conv_id = st.session_state.current_conv
    if conv_id is None:
        st.info("在左边新建或选择一个会话")
        return

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    prompt = st.chat_input("输入你的问题")
    if not prompt:
        return

    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        try:
            reply = st.write_stream(stream_chat(conv_id, prompt))
        except httpx.HTTPStatusError as exc:
            back_to_login_if_expired(exc)
            st.error(read_error(exc))
            return
        except (httpx.HTTPError, RuntimeError) as exc:
            st.error(f"对话失败：{exc}")
            return

    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.messages.append({"role": "assistant", "content": reply})

    # 刚聊过的会话会排到最前，重画侧边栏
    with contextlib.suppress(httpx.HTTPError):
        load_conversations()


init_state()

if st.session_state.token is None:
    show_login()
else:
    show_chat()
