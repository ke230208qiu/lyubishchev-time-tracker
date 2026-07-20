from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.tools import tool   # 如需给工具加装饰器，可用此导入
from datetime import datetime
# 导入全局配置
from config import SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL, LLM_MODEL

# 导入全部自定义工具
from tools.asr_tool import audio_to_text
from tools.record_parse_tool import parse_and_save_record
from tools.query_record_tool import query_time_record
from tools.report_tool import generate_time_analysis_report

# 1. 初始化模型
model = ChatOpenAI(
    api_key=SILICONFLOW_API_KEY,
    base_url=SILICONFLOW_BASE_URL,
    model=LLM_MODEL,
    temperature=0
)

# 2. 工具列表
tools = [
    audio_to_text,
    parse_and_save_record,
    query_time_record,
    generate_time_analysis_report
]

# 3. 系统提示词
current_date = datetime.now().strftime("%Y年%m月%d日")
system_prompt = f"""你是柳比歇夫时间记录管理助手，拥有4个工具，严格按照用户需求自动调度工具，禁止编造不存在的时间记录数据：
### 关于时间的重点
重点：当前日期是：{current_date}，你必须根据当前日期和用户说的话综合分析，具体要查的日期是什么
### 工具说明
1. audio_to_text(audio_file_path: str) —— 将mp3/wav语音转纯文本
2. parse_and_save_record(voice_raw_text: str, custom_prompt="提取全天所有时间段活动") —— 提取时间段、活动、分类、时长，存入MongoDB
3. query_time_record(start_date: str, end_date: str) —— 查询指定区间全部时间记录
4. generate_time_analysis_report(record_data_json, start_date, end_date, model_name="zai-org/GLM-5.2", custom_prompt="", output_format="text_with_echarts") —— 生成文字分析报告+ECharts图表配置

### 业务执行规则
场景1：用户录入当日时间记录
① 用户提供音频文件路径：先调用audio_to_text转文字，再调用parse_and_save_record入库；
② 用户直接口述文字：直接调用parse_and_save_record，不需要语音工具；

场景2：用户想查看某天/某几天原始记录
直接调用query_time_record，把查到的原始记录整理清晰返回；

场景3：用户想要分析、复盘、生成图表报告
第一步：先调用query_time_record获取数据；
第二步：调用generate_time_analysis_report生成图文分析报告；

### 异常处理规则
工具返回【失败】开头的错误信息时，直接把错误原文整理告知用户；
禁止自己编造时间记录、日期、活动数据，所有数据必须来自数据库查询结果。
"""

# 4. 创建 Agent（LangChain 1.0 统一入口）
agent = create_agent(
    model=model,
    tools=tools,
    system_prompt=system_prompt
)

# 5. 交互入口
if __name__ == "__main__":
    print("===== 柳比歇夫时间记录Agent 启动完成 =====")
    print("可用指令示例：")
    print("1. 解析音频 test2.mp3 并保存记录")
    print("2. 查询2026-07-08的全部时间记录")
    print("3. 生成2026-07-01至2026-07-08时间分析报告")
    print("输入 exit 退出\n")

    while True:
        user_input = input("请输入你的需求：")
        if user_input.strip().lower() == "exit":
            print("程序退出")
            break
        try:
            # LangChain 1.0 调用格式：必须传 messages 列表
            result = agent.invoke({
                "messages": [{"role": "user", "content": user_input}]
            })
            # 取最后一条消息作为最终回复
            final_message = result["messages"][-1]
            print("\n【助手回复】\n", final_message.content, "\n")
        except Exception as e:
            print(f"\n【系统异常】{str(e)}\n")