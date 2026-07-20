# 解析语音文本，结构化提取时间记录并存入MongoDB
import json
from typing import List, Optional
from pydantic import BaseModel, Field
from openai import APIError
from datetime import date
from typing import Literal
from langchain.tools import tool
import os
from pymongo.errors import PyMongoError

# 从 config 统一导入配置
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import llm_client, record_coll, LLM_MODEL

# ========== 创建复合索引，加速查询 ==========
record_coll.create_index([("user_id", 1), ("date", -1)], unique=False)

# 数据模型定义
class TimeSlot(BaseModel):
    start_time: str = Field(description="开始时间，格式：HH:MM（如08:30）")
    end_time: str = Field(description="结束时间，格式：HH:MM（如10:00）")
    activity: str = Field(description="具体活动内容（如写代码、看电影）")
    category: Literal["工作", "学习", "娱乐", "运动", "其他"] = Field(description="活动分类")
    duration: float = Field(description="时长（小时，如1.5）")

class DailyRecord(BaseModel):
    user_id: str = Field(default="", description="飞书用户ID")
    date: str = Field(
        default_factory=lambda: date.today().strftime("%Y-%m-%d"),
        description="记录日期，格式：YYYY-MM-DD"
    )
    start_time: str = Field(description="起床时间，格式：HH:MM")
    end_time: str = Field(description="睡觉时间，格式：HH:MM")
    time_slots: list[TimeSlot] = Field(description="一天中所有时间段的活动记录")

def get_structure_output(raw_text: str, prompt: str) -> Optional[str]:
    """调用LLM提取结构化JSON，返回清洗后的字符串，失败返回None"""
    raw_text = raw_text.strip()
    if not raw_text:
        print("错误：输入语音文本为空")
        return None

    today = date.today().strftime("%Y-%m-%d")
    system_prompt = f"""你是时间记录提取助手，严格按照要求输出。
1. date默认使用今日日期{today}，用户明确说明其他日期才修改；
2. 仅输出标准JSON，禁止```、注释、说明文字、换行多余描述；
3. 所有字段必须完整，数值使用数字类型，字符串使用双引号；
输出结构规范：
{DailyRecord.model_json_schema()}
"""
    try:
        resp = llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"语音原文：{raw_text}\n提取要求：{prompt}"}
            ],
            temperature=0,
            stream=False
        )
        json_content = resp.choices[0].message.content.strip()
        json_content = json_content.removeprefix("```json").removeprefix("```")
        json_content = json_content.removesuffix("```").strip()
        return json_content
    except APIError as e:
        print(f"LLM接口请求异常：{e}")
        return None
    except Exception as e:
        print(f"结构化提取未知异常：{e}")
        return None

# ========== 修改：insert_daily_record 加 user_id 参数 ==========
def insert_daily_record(data_dict: dict, user_id: str) -> str:
    """追加每日时间记录，使用原子操作防止并发覆盖"""
    try:
        record_model = DailyRecord(**data_dict)
        valid_data = record_model.model_dump()
        record_date = valid_data["date"]
        new_slots = valid_data.get("time_slots", [])

        if not new_slots:
            return "没有可入库的时间段数据"

        # ========== 修改：用原子操作替代 find_one + replace_one ==========
        # 计算新slots的最早和最晚时间
        all_starts = [s["start_time"] for s in new_slots]
        all_ends = [s["end_time"] for s in new_slots]
        min_start = min(all_starts)
        max_end = max(all_ends)

        result = record_coll.find_one_and_update(
            {"user_id": user_id, "date": record_date},
            {
                "$push": {"time_slots": {"$each": new_slots}},
                "$min": {"start_time": min_start},
                "$max": {"end_time": max_end},
                "$setOnInsert": {"user_id": user_id, "date": record_date}
            },
            upsert=True,
            return_document=False  # 不需要返回文档，只要知道成功了
        )

        # 查一下现在总共有多少条
        current_doc = record_coll.find_one({"user_id": user_id, "date": record_date})
        total_slots = len(current_doc.get("time_slots", [])) if current_doc else len(new_slots)

        if result:
            return f"数据追加成功（合并 {len(new_slots)} 条记录，当天共 {total_slots} 条）"
        else:
            return f"数据入库成功（新建当日记录，共 {len(new_slots)} 条）"

    except PyMongoError as e:
        err_msg = f"MongoDB写入失败：{str(e)}"
        print(err_msg)
        return err_msg
    except Exception as e:
        err_msg = f"数据校验/入库失败：{str(e)}"
        print(err_msg)
        return err_msg

# ========== 修改：tool 加 user_id 参数 ==========
@tool
def parse_and_save_record(
    voice_raw_text: str,
    custom_prompt: str = "提取全天所有时间段活动",
    user_id: str = ""
) -> str:
    """
    接收语音识别文本，LLM结构化提取时间记录，校验后存入MongoDB
    Args:
        voice_raw_text: ASR识别后的纯文本内容
        custom_prompt: 自定义提取规则，可选
        user_id: 飞书用户唯一标识（union_id），必填
    Returns:
        完整入库/失败提示文案
    """
    try:
        json_str = get_structure_output(raw_text=voice_raw_text, prompt=custom_prompt)
        if not json_str:
            return "【失败】LLM结构化提取无返回内容"

        raw_data = json.loads(json_str)

        # ========== 修改：直接用传入的 user_id 参数，不依赖全局上下文 ==========
        raw_data["user_id"] = user_id

        if not user_id:
            return "【失败】user_id 为空，无法保存数据，请确认用户身份"

        save_msg = insert_daily_record(raw_data, user_id=user_id)
        record_date = raw_data.get("date", date.today().strftime("%Y-%m-%d"))
        return f"【成功】{save_msg}，记录日期：{record_date}"

    except json.JSONDecodeError as e:
        return f"【失败】LLM输出JSON格式错误，错误信息：{str(e)}，原始输出：{json_str}"
    except Exception as e:
        return f"【失败】解析入库流程异常：{str(e)}"