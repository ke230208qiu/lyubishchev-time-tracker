#语音转文字
#导入依赖
import requests
from json import JSONDecodeError
from requests import RequestException
from langchain.tools import tool

# 从 config 统一导入配置
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import SILICONFLOW_API_KEY, ASR_URL, ASR_MODEL, SUPPORT_AUDIO_SUFFIX

def silico_asr(file_path: str) -> dict | None:
    """调用硅基流语音转文字接口，失败返回None"""
    headers = {"Authorization": f"Bearer {SILICONFLOW_API_KEY}"}
    if not file_path.lower().endswith(SUPPORT_AUDIO_SUFFIX):
        print(f"文件格式不支持，仅允许{SUPPORT_AUDIO_SUFFIX}")
        return None
    try:
        with open(file_path, "rb") as audio_file:
            files = {"file": ("audio.mp3", audio_file, "audio/mpeg"), "model": (None, ASR_MODEL)}
            response = requests.post(ASR_URL, headers=headers, files=files, timeout=15)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"ASR请求失败，状态码: {response.status_code}，响应内容：{response.text}")
            return None
    except FileNotFoundError:
        print(f"文件不存在：{file_path}")
    except ConnectionError:
        print("网络连接失败，无法访问ASR接口")
    except requests.exceptions.Timeout:
        print("ASR接口请求超时")
    except JSONDecodeError:
        print("接口返回非标准JSON数据")
    except RequestException as e:
        print(f"网络请求异常：{type(e).__name__} - {str(e)}")
    except Exception as e:
        print(f"未知异常：{type(e).__name__} - {str(e)}")
    return None

@tool
def audio_to_text(audio_file_path: str) -> str:
    """
    将本地音频文件转为文字，用于提取每日时间记录
    Args:
        audio_file_path: 本地音频文件绝对路径，仅支持mp3/wav格式
    Returns:
        语音识别后的纯文本内容；识别失败返回错误描述字符串
    """
    try:
        asr_result = silico_asr(audio_file_path)
        if not asr_result:
            return "语音识别接口调用失败，请检查音频文件或网络配置"
        text = asr_result.get("text", "")
        return text.strip()
    except Exception as e:
        err_msg = f"语音解析异常：{str(e)}"
        print(err_msg)
        return err_msg