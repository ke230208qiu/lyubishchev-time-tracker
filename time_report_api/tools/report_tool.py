# 大模型生成时间管理图文分析报告
import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Literal, Optional
from langchain.tools import tool
from openai import APIError
from utils.echarts_renderer import render_charts

# 从 config 统一导入配置
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import llm_client, LLM_MODEL


def preprocess_data(data_json: str) -> dict:
    """
    Python 预处理原始 JSON 数据，生成统计摘要。
    所有聚合计算在这里完成，不传给 LLM 做。
    """
    try:
        records = json.loads(data_json)
    except (json.JSONDecodeError, TypeError):
        # 可能是 Python 的 list/dict 被 str() 了，先 eval 再 json
        try:
            records = eval(data_json)
            if isinstance(records, str):
                records = json.loads(records)
        except Exception:
            return {"has_data": False, "error": "数据解析失败"}

    if not records:
        return {"has_data": False}

    # 统一转成 list
    if isinstance(records, dict):
        records = [records]

    category_hours = defaultdict(float)
    activity_hours = defaultdict(float)
    daily_hours = defaultdict(float)
    daily_slot_count = defaultdict(int)
    all_slots = []

    for record in records:
        record_date = record.get("date", "")
        slots = record.get("time_slots", [])
        day_total = 0.0
        for slot in slots:
            duration = float(slot.get("duration", 0))
            cat = slot.get("category", "其他")
            act = slot.get("activity", "未知")

            category_hours[cat] += duration
            activity_hours[act] += duration
            day_total += duration
            all_slots.append({
                "date": record_date,
                "activity": act,
                "category": cat,
                "duration": duration,
                "start_time": slot.get("start_time", ""),
                "end_time": slot.get("end_time", "")
            })
        daily_hours[record_date] = day_total
        daily_slot_count[record_date] = len(slots)

    total_hours = sum(category_hours.values())
    total_days = len(records)

    # TOP活动（前10）
    top_activities = sorted(activity_hours.items(), key=lambda x: -x[1])[:10]

    # 日均时长
    daily_avg = round(total_hours / total_days, 1) if total_days > 0 else 0

    # 找出时长最高/最低的活动（异常检测）
    sorted_acts = sorted(activity_hours.items(), key=lambda x: -x[1])
    longest_activity = sorted_acts[0] if sorted_acts else ("", 0)
    shortest_activity = sorted_acts[-1] if sorted_acts else ("", 0)

    # 分类占比
    category_pct = {}
    for cat, hours in category_hours.items():
        category_pct[cat] = {
            "hours": round(hours, 1),
            "pct": round(hours / total_hours * 100, 1) if total_hours > 0 else 0
        }

    # 单日数据时，检查时段完整性（从起床到睡觉中间有没有大段空白）
    blank_periods = []
    if total_days == 1 and all_slots:
        slots_sorted = sorted(all_slots, key=lambda x: x["start_time"])
        for i in range(len(slots_sorted) - 1):
            curr_end = slots_sorted[i]["end_time"]
            next_start = slots_sorted[i + 1]["start_time"]
            if curr_end and next_start:
                try:
                    h1, m1 = map(int, curr_end.split(":"))
                    h2, m2 = map(int, next_start.split(":"))
                    gap = (h2 * 60 + m2) - (h1 * 60 + m1)
                    if gap > 120:  # 空白超过2小时
                        blank_periods.append(f"{curr_end}-{next_start}（空白{gap}分钟）")
                except ValueError:
                    pass

    return {
        "has_data": True,
        "total_days": total_days,
        "total_hours": round(total_hours, 1),
        "daily_avg": daily_avg,
        "category_stats": dict(category_hours),
        "category_pct": category_pct,
        "top_activities": [(a, round(h, 1)) for a, h in top_activities],
        "longest_activity": (longest_activity[0], round(longest_activity[1], 1)),
        "shortest_activity": (shortest_activity[0], round(shortest_activity[1], 1)),
        "blank_periods": blank_periods,
        "daily_slot_count": dict(daily_slot_count),
    }


def generate_echarts_charts(summary: dict) -> list[dict]:
    """
    Python 直接生成 ECharts 图表配置，不依赖 LLM。
    比让 LLM 生成 JSON 更快、更准确。
    """
    charts = []

    # ---------- 饼图：分类占比 ----------
    pie_data = []
    for cat, info in sorted(summary["category_pct"].items(), key=lambda x: -x[1]["hours"]):
        pie_data.append({"name": cat, "value": info["hours"]})

    if pie_data:
        charts.append({
            "chart_type": "pie",
            "echarts_option": {
                "title": {"text": "时间分类占比", "left": "center"},
                "tooltip": {"trigger": "item", "formatter": "{b}: {c}h ({d}%)"},
                "legend": {"orient": "vertical", "left": "left"},
                "series": [{
                    "type": "pie",
                    "radius": ["40%", "70%"],
                    "avoidLabelOverlap": False,
                    "itemStyle": {"borderRadius": 10, "borderColor": "#fff", "borderWidth": 2},
                    "label": {"show": False, "position": "center"},
                    "emphasis": {
                        "label": {"show": True, "fontSize": 20, "fontWeight": "bold"}
                    },
                    "data": pie_data
                }]
            }
        })

    # ---------- 柱状图：TOP活动 ----------
    top_acts = summary["top_activities"][:8]
    if top_acts:
        charts.append({
            "chart_type": "bar",
            "echarts_option": {
                "title": {"text": "主要活动时长TOP", "left": "center"},
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {
                    "type": "category",
                    "data": [a[0] for a in top_acts],
                    "axisTick": {"alignWithLabel": True},
                    "axisLabel": {"rotate": 30, "interval": 0}
                },
                "yAxis": {"type": "value", "name": "小时"},
                "series": [{
                    "type": "bar",
                    "barWidth": "60%",
                    "data": [a[1] for a in top_acts],
                    "itemStyle": {"color": "#5470c6"}
                }]
            }
        })

    return charts


def generate_text_analysis(summary: dict, custom_prompt: str = "") -> str:
    """
    调用 LLM 只写分析文字。
    传给 LLM 的是预处理后的简短摘要，prompt 很短，响应很快。
    """
    if not summary.get("has_data"):
        return "暂无数据可供分析。"

    summary_text = f"""【统计摘要】
统计周期：{summary['total_days']}天
总记录时长：{summary['total_hours']}小时
日均时长：{summary['daily_avg']}小时

分类统计：
"""
    for cat, info in sorted(summary["category_pct"].items(), key=lambda x: -x[1]["hours"]):
        summary_text += f"  {cat}: {info['hours']}小时（占比{info['pct']}%）\n"

    summary_text += "\n主要活动TOP10：\n"
    for act, hours in summary["top_activities"]:
        summary_text += f"  {act}: {hours}小时\n"

    summary_text += f"\n最长活动：{summary['longest_activity'][0]}（{summary['longest_activity'][1]}小时）\n"
    summary_text += f"最短活动：{summary['shortest_activity'][0]}（{summary['shortest_activity'][1]}小时）\n"

    if summary["blank_periods"]:
        summary_text += f"\n时段空白：{', '.join(summary['blank_periods'])}\n"
    else:
        summary_text += "\n时段空白：无明显大段空白\n"

    system_prompt = """你是专业时间管理分析师。基于提供的统计摘要，写一份详细、有深度的分析报告。

要求：
1. 报告分4个模块，每个模块至少写2-3句详细分析：
   ① 时间分配总结：概述各分类占比特征，分析时间分配的整体倾向和规律；
   ② 趋势分析：如果是多天数据，逐日对比时长变化趋势；如果是单日，详细分析时段记录的完整性，指出有无大段空白及其可能原因；
   ③ 异常数据说明：深入分析时长过高或过低的活动，结合生活/工作场景给出合理解释；
   ④ 优化建议：给出3-5条具体、可执行的提升建议，每条详细展开1-2句，不要泛泛而谈；
2. 文字自然流畅，纯文本段落，不用markdown、表格、加粗等格式；
3. 只输出分析文字，不要输出JSON、图表配置、数据表格等。"""

    if custom_prompt:
        system_prompt += f"\n\n用户额外要求：{custom_prompt}"

    try:
        resp = llm_client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0.7,
            stream=False,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": summary_text}
            ]
        )
        return resp.choices[0].message.content.strip()
    except APIError as e:
        print(f"LLM文字分析请求失败：{e}")
        # 降级：用模板生成简单分析
        return _fallback_analysis(summary)


def _fallback_analysis(summary: dict) -> str:
    """LLM 超时或失败时的降级文案"""
    text = f"""时间分配总结：
统计周期共{summary['total_days']}天，累计记录{summary['total_hours']}小时，日均{summary['daily_avg']}小时。
"""
    text += "各分类时长："
    for cat, info in sorted(summary["category_pct"].items(), key=lambda x: -x[1]["hours"]):
        text += f"{cat}{info['hours']}小时（{info['pct']}%），"
    text = text.rstrip("，") + "。\n\n"

    if summary["blank_periods"]:
        text += f"时段空白：{', '.join(summary['blank_periods'])}。\n\n"

    text += "优化建议：\n"
    text += "1. 建议关注时长占比较高的活动，评估是否投入合理。\n"
    text += "2. 如有大段空白时段，建议补充记录，提升时间追踪完整性。\n"
    text += "3. 尝试为耗时较长的活动设定明确目标，提高单位时间产出。\n"
    return text


@tool
def generate_time_analysis_report(
    record_data_json: str,
    start_date: str,
    end_date: str,
    custom_prompt: str = "",
    output_format: str = "text_with_echarts",
    user_id: str = ""
) -> str:
    """
    根据日期区间记录生成标准图文分析报告，返回 JSON 字符串。
    数据预处理、图表生成用 Python 完成，LLM 只负责写分析文字，速度快、稳定。
    Args:
        record_data_json: query_time_record 返回的时间记录 JSON 字符串
        start_date: 分析起始日期 YYYY-MM-DD
        end_date: 分析结束日期 YYYY-MM-DD
        custom_prompt: 用户自定义分析要求，可选
        output_format: text_only / text_with_echarts
        user_id: 飞书用户唯一标识（union_id），必填
    Returns:
        成功：包含 report_text 和 charts 的 JSON；失败：【失败】开头的错误提示
    """
    if output_format not in ("text_only", "text_with_echarts"):
        return f"【失败】output_format 仅支持 text_only / text_with_echarts，传入值：{output_format}"

    # 1. Python 预处理数据（毫秒级）
    summary = preprocess_data(record_data_json)
    if not summary.get("has_data"):
        return "【失败】暂无数据可供分析"

    # 2. Python 生成图表配置（毫秒级）
    charts = []
    if output_format == "text_with_echarts":
        charts = generate_echarts_charts(summary)

    # 3. LLM 只写分析文字（prompt 很短，几秒完成）
    report_text = generate_text_analysis(summary, custom_prompt)

    # 4. 渲染图表为 PNG（传入 user_id，避免并发冲突）
    if output_format == "text_with_echarts":
        try:
            render_charts(record_data_json, user_id=user_id, output_dir="./temp_charts")
        except Exception as e:
            print(f"图表渲染失败：{e}")

    # 5. 组装结果
    result = {
        "report_text": report_text,
        "charts": charts,
        "generated_at": datetime.now().isoformat()
    }
    return json.dumps(result, ensure_ascii=False, indent=2)