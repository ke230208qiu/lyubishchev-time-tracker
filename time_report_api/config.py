from dotenv import load_dotenv
import os
from openai import OpenAI
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# 1. 加载.env文件
ENV_PATH = os.path.join(os.path.dirname(__file__), "配置.env")
load_dotenv(dotenv_path=ENV_PATH)

# 2. 读取所有环境变量
# MongoDB
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB")
MONGO_COLL_NAME = os.getenv("MONGO_COLL")

# 硅基流
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL")
ASR_MODEL = os.getenv("ASR_MODEL")
LLM_MODEL = os.getenv("LLM_MODEL")
ASR_URL = f"{SILICONFLOW_BASE_URL}/audio/transcriptions"

# 飞书
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# 3. 全局前置校验：缺失配置直接抛出清晰错误
required_configs = [
    MONGO_URI, MONGO_DB_NAME, MONGO_COLL_NAME,
    SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL, ASR_MODEL, LLM_MODEL
]
if not all(required_configs):
    raise RuntimeError("配置.env缺少必填项，请检查Mongo、硅基流密钥、模型配置")

# 4. 全局单例 LLM 客户端（全局复用，只创建一次）
llm_client = OpenAI(
    api_key=SILICONFLOW_API_KEY,
    base_url=SILICONFLOW_BASE_URL,
    timeout=120.0
)

# 5. 全局单例 MongoDB 连接（全局复用）
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[MONGO_DB_NAME]
    record_coll = db[MONGO_COLL_NAME]
except PyMongoError as e:
    raise RuntimeError(f"MongoDB 连接失败：{str(e)}")

# 6. 全局常量（模型白名单、格式约束）
SUPPORT_AUDIO_SUFFIX = (".mp3", ".wav")
OUTPUT_FORMAT_OPTIONS = ("text_only", "text_with_echarts")