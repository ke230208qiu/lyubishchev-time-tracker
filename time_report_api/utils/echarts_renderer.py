# utils/echarts_renderer.py
import os
import ast
import json
import plotly.express as px
import plotly.graph_objects as go
from datetime import date

# 莫兰迪渐变色系
MORANDI_COLORS = [
    "#457B9D",  # 雾蓝 - 工作
    "#E09F3E",  # 暖杏 - 其他
    "#E07A5F",  # 珊瑚 - 娱乐
    "#76C893",  # 豆绿 - 学习
    "#9D4EDD",  # 薰衣草 - 运动
    "#E76F51",  # 赭石
    "#2A9D8F",  # 青碧
    "#F4A261",  # 琥珀
]

PIE_COLORS = [
    ["#A8DADC", "#457B9D"],  # 雾蓝渐变对
    ["#F2CC8F", "#E09F3E"],  # 暖杏渐变对
    ["#FFB4A2", "#E07A5F"],  # 珊瑚渐变对
    ["#B5E48C", "#76C893"],  # 豆绿渐变对
    ["#CDB4DB", "#9D4EDD"],  # 薰衣草渐变对
]

def _extract_chart_data(record_data_json: str) -> dict:
    """从时间记录JSON中提取按分类统计的时长"""
    records = None
    # 先尝试标准 JSON
    try:
        records = json.loads(record_data_json)
    except (json.JSONDecodeError, TypeError):
        pass
    
    # 再尝试 Python 的 repr 格式（单引号）
    if records is None:
        try:
            records = ast.literal_eval(record_data_json)
        except Exception:
            pass
    
    if records is None:
        return {"解析失败": 1}
    
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        return {"解析失败": 1}
    
    category_stats = {}
    for record in records:
        for slot in record.get("time_slots", []):
            category = slot.get("category", "其他")
            duration = slot.get("duration", 0)
            category_stats[category] = category_stats.get(category, 0) + duration
    return category_stats if category_stats else {"无数据": 1}

def render_charts(record_data_json: str, user_id: str = "", output_dir: str = "./temp_charts") -> list[str]:
    """用 Plotly 生成莫兰迪风格高质量图表"""
    os.makedirs(output_dir, exist_ok=True)

    report_data = _extract_chart_data(record_data_json)
    categories = list(report_data.keys())
    values = list(report_data.values())
    total = sum(values)
    image_paths = []

    n = len(categories)
    pie_colors = [PIE_COLORS[i % len(PIE_COLORS)][0] for i in range(n)]
    bar_colors = [MORANDI_COLORS[i % len(MORANDI_COLORS)] for i in range(n)]

    # 文件名加用户前缀，防并发冲突
    prefix = user_id.replace("-", "") if user_id else "default"

    # ===== 环形图 =====
    pie_path = os.path.join(output_dir, f"{prefix}_pie.png")
    fig_pie = go.Figure(data=[go.Pie(
        labels=categories,
        values=values,
        hole=0.55,
        textinfo="label+percent",
        textposition="outside",
        textfont=dict(size=13, color="#4A5568", family="Arial"),
        marker=dict(
            colors=pie_colors,
            line=dict(color="#FFFFFF", width=2.5),
        ),
        pull=[0.03] * n,
        hovertemplate="<b>%{label}</b><br>时长: %{value:.1f}h<br>占比: %{percent}<extra></extra>",
    )])
    fig_pie.update_layout(
        title=dict(
            text="时间分配占比",
            font=dict(size=18, color="#1D3557", family="Arial"),
            x=0.5, xanchor="center",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=-0.12,
            xanchor="center", x=0.5,
            font=dict(size=12, color="#4A5568"),
        ),
        annotations=[dict(
            text=f"<b>{total:.1f}</b><br><span style='font-size:11px;color:#9BA4B4'>总时长(小时)</span>",
            x=0.5, y=0.5,
            font=dict(size=22, color="#1D3557"),
            showarrow=False,
        )],
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        width=800, height=520,
        margin=dict(t=70, b=80, l=40, r=40),
        showlegend=False,
    )
    # 手动添加图例到图表中
    for i, cat in enumerate(categories):
        pct = values[i] / total * 100 if total > 0 else 0
        fig_pie.add_annotation(
            dict(
                x=1.18, y=0.9 - i * 0.12,
                text=f'<span style="font-size:13px">●</span> {cat}  <b>{values[i]:.1f}h</b>  <span style="color:#9BA4B4">{pct:.1f}%</span>',
                font=dict(size=12, color="#4A5568"),
                showarrow=False,
                xanchor="left",
            )
        )
    fig_pie.write_image(pie_path, scale=2)
    image_paths.append(pie_path)

    # ===== 柱状图 =====
    bar_path = os.path.join(output_dir, f"{prefix}_bar.png")
    fig_bar = go.Figure(go.Bar(
        x=categories,
        y=values,
        marker=dict(
            color=bar_colors,
            line=dict(color="rgba(255,255,255,0.6)", width=1.5),
            cornerradius=6,
        ),
        text=[f"{v:.1f}h" for v in values],
        textposition="outside",
        textfont=dict(size=14, color="#1D3557", family="Arial"),
        hovertemplate="<b>%{x}</b><br>时长: %{y:.1f}h<extra></extra>",
    ))
    fig_bar.update_layout(
        title=dict(
            text="各活动时长统计",
            font=dict(size=18, color="#1D3557", family="Arial"),
            x=0.5, xanchor="center",
        ),
        xaxis=dict(
            title=dict(text="活动类型", font=dict(size=13, color="#718096")),
            tickfont=dict(size=13, color="#4A5568"),
            gridcolor="#F0F4F8",
            zerolinecolor="#E2E8F0",
            showgrid=False,
        ),
        yaxis=dict(
            title=dict(text="时长（小时）", font=dict(size=13, color="#718096")),
            tickfont=dict(size=11, color="#A0AEC0"),
            gridcolor="#F0F4F8",
            zerolinecolor="#E2E8F0",
            dtick=1,
        ),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        width=800, height=520,
        margin=dict(t=70, b=70, l=70, r=40),
        showlegend=False,
        bargap=0.35,
    )
    fig_bar.write_image(bar_path, scale=2)
    image_paths.append(bar_path)

    return image_paths