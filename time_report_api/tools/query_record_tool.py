# 数据库查询操作
from langchain.tools import tool
from pymongo.errors import PyMongoError
import json

# 从 config 统一导入配置
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import record_coll

# ========== 修改：加 user_id 参数 ==========
def get_mongodb_data(user_id: str, start_date: str, end_date: str) -> list[dict]:
    try:
        query = {
            "user_id": user_id,    # ← 用传入的 user_id，不用全局上下文
            "date": {
                "$gte": start_date,
                "$lte": end_date
            }
        }
        results = list(record_coll.find(query))
        for result in results:
            result["_id"] = str(result["_id"])
        return results
    except PyMongoError as e:
        raise Exception(f"数据库查询失败: {str(e)}")

# ========== 修改：tool 加 user_id 参数，修复括号错误 ==========
@tool
def query_time_record(
    start_date: str,
    end_date: str,
    user_id: str = ""
) -> str:
    """
    查询用户指定日期区间的柳比歇夫时间记录
    Args:
        start_date: 起始日期，格式YYYY-MM-DD
        end_date: 结束日期，格式YYYY-MM-DD
        user_id: 飞书用户唯一标识（union_id），必填
    Returns:
        字符串序列化后的时间记录列表
    """
    # ========== 修复：原来的 (start_date, end_date) 缺左括号 ==========
    data = get_mongodb_data(user_id, start_date, end_date)
    return json.dumps(data, ensure_ascii=False, default=str)