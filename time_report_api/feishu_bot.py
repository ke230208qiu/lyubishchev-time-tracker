# feishu_bot.py
import json
import requests
from flask import Flask, request
import os
import subprocess
import tempfile
from datetime import date
import threading

# 全局：已处理的 message_id 集合，防止飞书重推
processed_msg_ids = set()
msg_lock = threading.Lock()

# 从 config 统一导入配置
from config import (
    FEISHU_APP_ID as APP_ID,
    FEISHU_APP_SECRET as APP_SECRET,
    SILICONFLOW_API_KEY,
    SILICONFLOW_BASE_URL,
    LLM_MODEL,
)

# 导入工具
from tools.asr_tool import audio_to_text
from tools.record_parse_tool import parse_and_save_record
from tools.query_record_tool import query_time_record
from tools.report_tool import generate_time_analysis_report
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

# 初始化模型（全局复用）
model = ChatOpenAI(
    api_key=SILICONFLOW_API_KEY,
    base_url=SILICONFLOW_BASE_URL,
    model=LLM_MODEL,
    temperature=0,
    timeout=120
)

# ========== 修改1：不再在模块级别创建 agent，改为在每次请求中创建 ==========
# tools 列表也保持全局（tool 函数本身是无状态的，user_id 通过参数传入）
tools = [audio_to_text, parse_and_save_record, query_time_record, generate_time_analysis_report]

today = date.today().strftime("%Y-%m-%d")

# ========== 修改2：system_prompt 不再包含动态变量 ==========
BASE_SYSTEM_PROMPT = f"""你是柳比歇夫时间记录管理助手，当前日期是 {today}，你拥有4个工具：

1. audio_to_text(audio_file_path: str) —— 将mp3/wav语音转纯文本
2. parse_and_save_record(voice_raw_text: str, custom_prompt="提取全天所有时间段活动", user_id: str) —— 提取时间段、活动、分类、时长，存入MongoDB。user_id 必填
3. query_time_record(start_date: str, end_date: str, user_id: str) —— 查询指定区间全部时间记录。user_id 必填
4. generate_time_analysis_report(record_data_json, start_date, end_date, custom_prompt="", output_format="text_with_echarts", user_id: str) —— 生成文字分析报告+图表。user_id 必填

业务规则：
- 用户录入时间记录（文字/语音）：调用 parse_and_save_record
- 用户查看记录：调用 query_time_record
- 用户要分析报告：先 query_time_record 获取数据，再 generate_time_analysis_report 生成报告
- 禁止编造数据，所有数据来自数据库查询"""

app = Flask(__name__)

def get_tenant_access_token() -> str:
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/",
        json={"app_id": APP_ID, "app_secret": APP_SECRET}
    )
    return resp.json().get("tenant_access_token", "")

def send_text_message(chat_id: str, text: str, token: str):
    requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text})
        }
    )

def download_feishu_file(message_id: str, file_key: str, token: str, save_path: str):
    """下载飞书消息中的文件"""
    resp = requests.get(
        f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}",
        headers={"Authorization": f"Bearer {token}"},
        params={"type": "file"}
    )
    with open(save_path, "wb") as f:
        f.write(resp.content)

def convert_opus_to_wav(opus_path: str, wav_path: str):
    """用 FFmpeg 将音频转为 wav，自动检测输入格式"""
    file_size = os.path.getsize(opus_path) if os.path.exists(opus_path) else 0
    print(f"音频文件大小: {file_size} 字节")
    with open(opus_path, "rb") as f:
        header = f.read(16)
        print(f"文件头(hex): {header.hex()}")

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", opus_path, "-ar", "16000", "-ac", "1", wav_path],
        capture_output=True, text=True
    )
    print(f"ffmpeg stderr: {result.stderr[-500:]}")
    result.check_returncode()

def upload_image(image_path: str, token: str) -> str:
    with open(image_path, "rb") as f:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"image": f},
            data={"image_type": "message"}
        )
    return resp.json().get("data", {}).get("image_key", "")

def send_image_message(chat_id: str, image_key: str, token: str):
    requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "receive_id": chat_id,
            "msg_type": "image",
            "content": json.dumps({"image_key": image_key})
        }
    )

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    # URL 验证
    if data and "challenge" in data:
        return {"challenge": data["challenge"]}

    # 解析消息
    event = data.get("event", {}) if data else {}
    message = event.get("message", {})

    # ========== 修改3：优先取 union_id ==========
    sender = event.get("sender", {})
    sender_id_obj = sender.get("sender_id", {})
    user_id = (
        sender_id_obj.get("union_id", "")
        or sender_id_obj.get("open_id", "")
        or sender_id_obj.get("user_id", "")
        or "unknown"
    )
    
    msg_type = message.get("message_type", "") or message.get("msg_type", "")
    chat_id = message.get("chat_id", "")
    message_id = message.get("message_id", "")
    content = json.loads(message.get("content", "{}"))
    print(f"收到消息，用户ID: {user_id}, 消息类型: {msg_type}")

    # 去重
    with msg_lock:
        if message_id in processed_msg_ids:
            return {"code": 0}
        processed_msg_ids.add(message_id)

    token = get_tenant_access_token()

    # 提取用户输入
    if msg_type in ("text", "post"):
        user_text = content.get("text", "")

    elif msg_type == "audio":
        user_text = None  # 后台处理

    else:
        print(f"收到未处理的消息类型: {msg_type}")
        send_text_message(chat_id, f"目前仅支持文字和语音消息，收到类型：{msg_type}", token)
        return {"code": 0}

    # 立刻回复，避免飞书超时
    if user_text:
        send_text_message(chat_id, "收到，正在处理中...", token)
    elif msg_type == "audio":
        send_text_message(chat_id, "收到语音，正在识别...", token)

    # ========== 修改4：每次请求创建独立 agent，避免多用户共享 ==========
    # ========== 修改5：语音文件用临时目录，图表文件统一走 ./temp_charts ==========
    def process_in_background(current_user_id, current_msg_type, current_content):
        nonlocal user_text
        try:
            # 语音文件用临时目录处理
            with tempfile.TemporaryDirectory() as temp_dir:
                if user_text is None and current_msg_type == "audio":
                    file_key = current_content.get("file_key", "")
                    opus_path = os.path.join(temp_dir, f"{message_id}.opus")
                    wav_path = os.path.join(temp_dir, f"{message_id}.wav")

                    download_feishu_file(message_id, file_key, token, opus_path)
                    convert_opus_to_wav(opus_path, wav_path)
                    user_text = audio_to_text.invoke({"audio_file_path": wav_path})

            if not user_text:
                send_text_message(chat_id, "语音识别失败，未获取到文字内容", token)
                return

            # 每次请求创建独立的 agent，带当前用户ID
            system_prompt = (
                f"{BASE_SYSTEM_PROMPT}\n\n"
                f"【重要】当前用户的 user_id 为 \"{current_user_id}\"，"
                f"调用所有工具时，"
                f"必须将 user_id 参数设为 \"{current_user_id}\"。"
            )
            agent = create_agent(model=model, tools=tools, system_prompt=system_prompt)

            # 在用户消息里也带一下，双重保险
            prompt_with_user = (
                f"{user_text}\n\n"
                f"[系统信息：当前用户ID={current_user_id}]"
            )

            result = agent.invoke({"messages": [{"role": "user", "content": prompt_with_user}]})
            reply_text = result["messages"][-1].content
            send_text_message(chat_id, reply_text, token)

            # ========== 修改6：从 ./temp_charts 读取当前用户的图表并发送 ==========
            chart_dir = "./temp_charts"
            prefix = current_user_id.replace("-", "") if current_user_id else "default"
            if os.path.exists(chart_dir):
                sent_files = []
                for filename in os.listdir(chart_dir):
                    if filename.startswith(prefix) and filename.endswith(".png"):
                        image_path = os.path.join(chart_dir, filename)
                        image_key = upload_image(image_path, token)
                        if image_key:
                            send_image_message(chat_id, image_key, token)
                        sent_files.append(image_path)
                # 发送完后清理，避免堆积
                for f_path in sent_files:
                    if os.path.exists(f_path):
                        os.remove(f_path)

        except Exception as e:
            print(f"后台处理异常: {str(e)}")
            import traceback
            traceback.print_exc()
            send_text_message(chat_id, "处理失败，请稍后重试或换用文字消息", token)

    threading.Thread(
        target=process_in_background,
        args=(user_id, msg_type, content),
        daemon=True
    ).start()
    return {"code": 0}

if __name__ == "__main__":
    print("飞书机器人服务启动，端口 8080")
    app.run(host="0.0.0.0", port=8080, threaded=True)