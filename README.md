# InboxLens

InboxLens 是一个本地优先、只读运行的 AI 邮件简报助手。它从邮箱读取新增邮件，识别重点、行动项和时效信息，并把整理后的每日简报发送到指定邮箱。

它适合希望减少反复打开邮箱、快速判断哪些邮件需要处理、同时不希望工具自动改动原邮箱的用户。

## 适用范围

InboxLens 当前可以满足“AI 邮件简报助手”的核心需求：

- 从新增邮件中提炼重点，而不是把原文重新堆给用户。
- 区分需回复、需执行和仅知晓的邮件。
- 标出高优先级、安全提醒、账单、订单、会议、订阅和营销类邮件。
- 汇总 deadline、金额、订单号、附件信息等关键事实。
- 将同一邮件会话和同类低价值通知合并展示。
- 通过本地控制台、命令行或定时任务运行。
- 保持只读边界，不自动回复、不删除、不归档、不修改邮件状态。

它暂时不适合需要完整邮箱代理能力的场景，例如自动写回邮件、自动整理邮箱标签、跨多个邮箱统一搜索、附件全文解析、日历/任务系统双向同步，或像聊天机器人一样对整个历史邮箱做问答。

## 功能亮点

- **每日邮件简报**：生成 HTML 和纯文本双格式简报，可直接发送到你的收件邮箱。
- **优先级排序**：将邮件分为 `P0`、`P1`、`P2`，把最需要注意的内容放在前面。
- **行动项识别**：自动标记 `需回复`、`需执行`、`仅知晓`。
- **时效提醒**：识别常见日期、截止时间和“今天 / 明天 / 本周内 / by Monday”等表达。
- **邮件分类**：覆盖工作沟通、事务记录、账单财务、系统通知、资讯订阅、营销推广、社交协作平台等常见类型。
- **会话合并**：同一主题或同一邮件线程的多封新邮件会合并为一个条目。
- **噪音压缩**：订阅、营销和平台通知会按发件人聚合，减少简报长度。
- **个人规则**：可用本地规则覆盖特定发件人、主题或关键词的分类、优先级和备注。
- **可选 AI 增强**：支持 OpenAI-compatible Chat Completions 接口，用于低置信度分类和高价值邮件摘要。
- **本地控制台**：在浏览器中完成配置、诊断、试跑、预览、测试发送和查看运行记录。
- **安全试跑**：`dry-run` 会生成预览，不发送简报，也不会把邮件标记为已处理。
- **失败可见**：运行失败会记录状态，并可选发送失败通知邮件。

## 运行要求

- Python 3.10 或更高版本
- 支持 IMAP 的源邮箱账号
- 支持 SMTP 的发信邮箱账号
- 可选：OpenAI-compatible LLM API Key

许多邮箱服务商需要使用“应用专用密码”或“授权码”，而不是网页登录密码。请参考你的邮箱服务商文档开启 IMAP / SMTP 并生成专用凭证。

## 快速开始

```bash
git clone <repo-url>
cd EmailManager
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[html]"
.\.venv\Scripts\python.exe main.py console
```

macOS / Linux:

```bash
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e ".[html]"
./.venv/bin/python main.py console
```

控制台默认打开：

```text
http://127.0.0.1:8765
```

在控制台中填写 IMAP、SMTP、接收邮箱和可选 LLM 配置，然后依次执行：

1. 保存配置
2. 初始化数据库
3. 验证 IMAP / SMTP 登录
4. 试跑并生成预览
5. 发送 SMTP 测试邮件
6. 发送正式简报

## 配置

推荐使用本地控制台完成配置。也可以手动复制环境变量模板：

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

最小可用配置：

```env
IMAP_HOST=imap.example.com
IMAP_PORT=993
IMAP_USER=source@example.com
IMAP_PASSWORD=source_app_password_or_authorization_code
IMAP_FOLDER=INBOX

SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USER=sender@example.com
SMTP_PASSWORD=smtp_app_password_or_authorization_code
SMTP_FROM=sender@example.com
DIGEST_TO=receiver@example.com
SMTP_USE_SSL=true
SMTP_STARTTLS=false
```

可选 AI 配置：

```env
LLM_ENABLED=true
LLM_BASE_URL=https://api.openai.com/v1/chat/completions
LLM_API_KEY=your_api_key
LLM_MODEL=gpt-4o-mini
LLM_JSON_MODE=true
```

常用运行配置：

```env
DATABASE_PATH=data/inbox_lens.sqlite
INBOX_LENS_TIMEZONE=Europe/London
BOOTSTRAP_WINDOW_HOURS=24
RETENTION_DAYS=30
SEND_EMPTY_DIGEST=false
SEND_FAILURE_EMAIL=true
USER_RULES_PATH=config/rules.toml
```

## 个人规则

个人规则适合处理“总是很重要”或“总是不重要”的发件人和关键词。

```bash
cp config/rules.toml.example config/rules.toml
```

Windows PowerShell:

```powershell
Copy-Item config/rules.toml.example config/rules.toml
```

示例：

```toml
[[rules]]
sender_contains = "manager@example.com"
category = "个人/工作沟通"
priority = "P0"
action = "需回复"
note = "Direct manager"
```

## 日常使用

启动本地控制台：

```bash
python main.py console
```

生成或更新配置：

```bash
python main.py wizard
```

检查配置：

```bash
python main.py doctor
```

检查 IMAP / SMTP 网络连通性：

```bash
python main.py doctor --network
```

验证 IMAP / SMTP 登录，不发送邮件：

```bash
python main.py doctor --auth
```

生成样例简报：

```bash
python main.py render-sample
```

试跑并生成预览，不发送邮件：

```bash
python main.py run --dry-run --limit 10
```

发送正式简报：

```bash
python main.py run
```

发送 SMTP 测试邮件：

```bash
python main.py send-test
```

查看最近运行记录：

```bash
python main.py inspect
```

安装后也可以使用命令入口：

```bash
inbox-lens --help
inbox-lens run --dry-run --limit 10
```

预览文件默认写入 `out/last_digest.html` 和 `out/last_digest.txt`，运行状态默认写入 `data/inbox_lens.sqlite`。

## 定时运行

InboxLens 不常驻后台，适合由系统调度器定时触发。

Windows Task Scheduler 示例：

```powershell
$Action = New-ScheduledTaskAction -Execute "C:\path\to\EmailManager\.venv\Scripts\python.exe" -Argument "C:\path\to\EmailManager\main.py run"
$Trigger = New-ScheduledTaskTrigger -Daily -At 7:30am
Register-ScheduledTask -TaskName "InboxLensDailyDigest" -Action $Action -Trigger $Trigger
```

Cron 示例：

```cron
30 7 * * * /path/to/EmailManager/.venv/bin/python /path/to/EmailManager/main.py run
```

## Docker

使用 Docker Compose 启动本地控制台：

```bash
docker compose up --build
```

默认地址：

```text
http://127.0.0.1:8765
```

常用 Docker 命令：

```bash
docker compose run --rm inbox-lens inbox-lens doctor
docker compose run --rm inbox-lens inbox-lens render-sample
docker compose run --rm inbox-lens inbox-lens run --dry-run --limit 10
```

## 隐私与安全

- InboxLens 只读取邮件，不会自动回复、删除、归档或修改源邮箱。
- 默认不会把原始邮件正文写入本地数据库。
- 本地会保存运行记录、邮件元数据、分类结果和摘要，用于去重、排错和查看历史运行状态。
- LLM 默认关闭；启用后，经过清理和截断的邮件内容可能会发送到你配置的 LLM 服务。
- 邮件正文会被视为不可信内容；检测到可疑指令注入时，会跳过 LLM 调用并在简报中提示。
- `.env` 中包含邮箱凭证和 API Key，不应提交到公开仓库。

## 当前限制

- 目前使用 IMAP / SMTP 接入邮箱，不内置 Gmail 或 Outlook OAuth 授权流程。
- 不会自动写信、回复、删除、归档、移动邮件或修改标签。
- 不解析附件正文，只展示附件名称、类型和大小等信息。
- 不提供跨全量历史邮箱的自然语言问答。
- 多邮箱聚合、日历/任务系统同步和自动学习反馈尚未作为稳定功能提供。

## 故障排查

- 登录失败：优先确认邮箱已开启 IMAP / SMTP，并使用应用专用密码或授权码。
- 收不到简报：运行 `python main.py send-test` 验证 SMTP 配置，再检查垃圾邮件箱。
- 没有新邮件：运行 `python main.py inspect` 查看最近运行状态，或使用 `--dry-run --limit 10` 生成预览。
- HTML 简报不理想：安装 `.[html]` 可获得更好的 HTML 邮件正文转换效果。

## 开发与测试

安装开发依赖：

```bash
python -m pip install -e ".[dev,html]"
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

检查导入与语法：

```bash
python -m compileall -q inbox_lens tests
```
