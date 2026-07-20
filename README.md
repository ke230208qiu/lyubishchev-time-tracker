# 柳比歇夫时间记录助手

基于 LangChain Agent 的飞书机器人，支持语音录入每日时间记录，查询历史，并自动生成图文分析报告。

## 功能

- **语音录入** — 发送语音消息，自动转文字并结构化存入 MongoDB
- **文字录入** — 直接发送文字描述一天的活动，LLM 自动解析
- **时间查询** — 按日期区间查询历史时间记录
- **分析报告** — 自动生成时间分配分析报告，附环形图/柱状图
- **多用户隔离** — 按飞书 union_id 隔离数据，多人共用同一机器人

## 架构

```
飞书消息 → Flask Webhook → LangChain Agent
                              ├── ASR 语音转文字
                              ├── LLM 结构化解析 → MongoDB
                              ├── 数据库查询
                              └── Plotly 图表 + 文字分析
```

## 技术栈

- **Agent 框架**: LangChain
- **LLM / ASR**: 硅基流动 API (SiliconFlow)
- **数据库**: MongoDB
- **图表**: Plotly
- **消息通道**: 飞书自定义应用 Webhook

## 快速开始

### 1. 环境要求

- Python 3.10+
- MongoDB
- FFmpeg（语音消息转码用）

### 2. 安装依赖

```bash
pip install -r time_report_api/requirements.txt
```

### 3. 配置环境变量

复制模板并填入真实信息：

```bash
cp 配置.env.example time_report_api/配置.env
```

编辑 `配置.env`：

```
MONGO_URI=你的MongoDB连接地址
MONGO_DB=数据库名
MONGO_COLL=集合名
SILICONFLOW_API_KEY=你的硅基流动Key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
ASR_MODEL=语音识别模型名
LLM_MODEL=大语言模型名
FEISHU_APP_ID=飞书AppID
FEISHU_APP_SECRET=飞书AppSecret
```

### 4. 启动

```bash
cd time_report_api
python feishu_bot.py
```

服务默认监听 `0.0.0.0:8080`，将该地址配置为飞书应用的 Webhook 地址即可。

### 5. 终端调试模式

不需要飞书也能在终端测试：

```bash
cd time_report_api
python main_agent.py
```

## 飞书应用配置

1. 在飞书开放平台创建企业自建应用
2. 开启机器人能力
3. 配置事件订阅，Webhook URL 指向 `http://你的服务器:8080/webhook`
4. 订阅 `im:message` 事件
5. 权限申请：`im:message`、`im:resource`（下载文件）

## 项目结构

```
time_report_api/
├── config.py              # 统一配置入口
├── feishu_bot.py          # 飞书 Webhook 服务
├── main_agent.py          # 终端调试入口
├── requirements.txt       # 依赖清单
├── tools/
│   ├── asr_tool.py        # 语音转文字
│   ├── record_parse_tool.py  # 结构化解析 + 入库
│   ├── query_record_tool.py  # 数据库查询
│   └── report_tool.py     # 分析报告生成
└── utils/
    ├── __init__.py
    └── echarts_renderer.py   # Plotly 图表渲染
```

## License

MIT
