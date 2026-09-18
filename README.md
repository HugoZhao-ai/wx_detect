# 微信美股/期权交易动作告警

这是一个运行在 Windows 上的微信消息监控工具。它监听指定微信群中指定成员的文本和语音消息，使用本机 Faster-Whisper 将语音转成文字，再调用 DeepSeek 判断消息中是否包含明确的美股或美股期权交易动作。达到置信度阈值后，程序可以向指定微信联系人发送结构化告警，并可选择发起微信语音通话。

> 本项目只发送通知，不执行证券交易。模型可能误判或漏判，输出不构成投资建议。

## 工作流程

```text
指定微信群消息
    -> 只保留指定成员的文本和语音
    -> 语音在本机转写
    -> DeepSeek 识别交易动作
    -> SQLite 去重
    -> 微信发送告警
    -> 可选：发起微信语音通话
```

默认规则：

- 识别买入、卖出、做空、回补、加仓、减仓、开仓、平仓、滚仓、行权和撤单。
- 支持美股股票及美股 Call/Put 期权。
- 默认置信度阈值为 `0.70`。
- 相同结构化动作默认在 10 分钟内只告警一次。
- 每次启动创建一个本地会话 JSON，保存本次启动以来目标成员的全部消息。
- 每次有新消息时，将该会话 JSON 的完整内容发送给 DeepSeek，并只判断最新增量。
- 连续短消息可以合并理解，例如先发 `aapl 9/18 325p`，再发 `买9.25的`。

## 使用前须知

1. 仅支持 Windows，并依赖本机已经安装和登录的个人微信。
2. 项目自动使用当前 Windows 用户所登录的微信账号，不提供单独的微信账号选择项。
3. 当前微信账号必须已经加入目标群，并能找到接警联系人。
4. 实际发送消息或拨号时，微信必须运行，Windows 必须保持登录且不能锁屏。
5. 这是非官方微信自动化方案。微信升级可能造成数据库读取或界面自动化失效，也可能存在账号风控风险，建议使用专门的监控账号并控制告警频率。
6. 程序只能判断“通话发起动作是否成功”，不能判断对方是否接听。
7. 首次启动不会补发历史消息，只处理启动后收到的新消息。

## 一、准备工作

开始前请准备：

- Windows 10 或 Windows 11 电脑。
- 已安装并登录的微信客户端。
- 一个可用的 DeepSeek API Key。
- 至少约 2 GB 可用磁盘空间。
- 首次安装依赖和下载语音模型时可访问互联网。

DeepSeek API Key 请在 [DeepSeek 开放平台](https://platform.deepseek.com/)创建。不要把 Key 发给别人，也不要提交到 Git。

## 二、克隆项目

打开 PowerShell，执行：

```powershell
git clone https://github.com/HugoZhao-ai/wx_detect.git
cd wx_detect
```

如果电脑尚未安装 Git，可以先从 [Git 官方网站](https://git-scm.com/download/win)安装 Git for Windows。

## 三、安装项目

项目使用自己的 Python 3.12 便携运行时，不会修改系统 Python。在项目目录执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

`setup.ps1` 会下载便携 Python、安装依赖，并在首次运行时从 `.env.example` 创建 `.env`。

如果 PowerShell 提示无法运行脚本，请确认先执行了上面的 `Set-ExecutionPolicy -Scope Process Bypass`。这个设置只对当前 PowerShell 窗口有效。

## 四、配置 API Key、群聊和联系人

安装完成后，在项目根目录打开 `.env`：

```powershell
notepad .env
```

至少需要修改以下五项：

```dotenv
# 要监听的群聊名称，必须与微信中显示的群名完全一致
WECHAT_GROUP_NAME=你的群聊名称

# 要监听的群成员名称，可以填写该成员在群中的昵称或备注
WECHAT_TARGET_MEMBER=要监听的人名

# 收到交易信号后，告警要发送给谁
WECHAT_ALERT_CONTACT_REMARK=接警联系人的微信备注
WECHAT_ALERT_CONTACT_NICKNAME=接警联系人的微信昵称

# 在 DeepSeek 开放平台创建的 API Key
DEEPSEEK_API_KEY=sk-请替换成你自己的Key
```

注意：

- 群名必须精确匹配，并且只能匹配到一个群。
- 监听成员必须能通过群昵称或备注精确匹配，并且只能匹配到一个人。
- 接警联系人优先使用稳定、唯一的微信备注。程序会同时核对备注和昵称。
- 监听成员既可以是当前登录账号本人，也可以是群内其他成员。
- `.env` 已被 `.gitignore` 排除，不会被正常的 Git 提交上传。

第一次使用时请保留以下安全配置：

```dotenv
DRY_RUN=true
CALLS_ENABLED=false
SEND_ALERT_MESSAGE=true
```

| 配置 | 含义 |
| --- | --- |
| `DRY_RUN=true` | 只打印模拟告警，不真实发送消息或拨号 |
| `CALLS_ENABLED=false` | 禁止真实语音呼叫 |
| `SEND_ALERT_MESSAGE=true` | 正式模式下允许发送微信文字告警 |

## 五、下载和配置语音模型

项目使用 Faster-Whisper。默认配置适合没有独立显卡的普通电脑：

```dotenv
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
SILK_SAMPLE_RATE=24000
```

### 推荐：提前下载模型

完成 `setup.ps1` 和 `.env` 配置后，在项目目录执行：

```powershell
.\.runtime\Python312\python.exe -c "from wx_trade_alert.config import Settings; from wx_trade_alert.speech import SpeechTranscriber; SpeechTranscriber(Settings.load())._load_model(); print('语音模型准备完成')"
```

程序会根据 `.env` 中的 `WHISPER_MODEL` 下载模型，并保存到：

```text
data/models/
```

默认 `small` 模型下载量约数百 MB。下载完成后可以离线进行语音转写，但 DeepSeek 分类仍然需要联网。

也可以不提前下载：首次收到语音消息时，程序会自动下载模型。为了避免正式监控时长时间等待，建议提前下载。

### 模型选择

| 场景 | 建议配置 | 特点 |
| --- | --- | --- |
| 普通 CPU 电脑 | `small`、`cpu`、`int8` | 推荐默认值，部署最简单 |
| CPU 较慢或空间有限 | `base`、`cpu`、`int8` | 更快、更小，但准确率较低 |
| NVIDIA GPU | `large-v3`、`cuda`、`float16` | 更准确，但要求 NVIDIA 驱动及 CUDA 运行库 |

NVIDIA GPU 示例：

```dotenv
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
```

如果不确定 CUDA 环境是否完整，请先使用默认 CPU 配置跑通全部流程。

## 六、按顺序验证

### 1. 检查微信账号、群和联系人

先启动微信并登录目标账号，然后执行：

```powershell
.\doctor.ps1
```

正常情况下会显示：

```text
[OK] 微信数据库可读取
[OK] 当前账号：...
[OK] 群聊：...
[OK] 监听成员：...
[OK] 接警联系人：...
[安全状态] DRY_RUN=True, CALLS_ENABLED=False
```

务必核对“当前账号”是否是准备用来运行监控的微信账号。如果不是，请停止项目，切换微信账号后再次运行 `doctor.ps1`。

### 2. 验证实时消息监听

```powershell
.\probe.ps1 -Seconds 120
```

在接下来的 120 秒内，让目标成员在目标群里分别发送一条文字和一条语音。终端应该打印捕获到的消息信息。此步骤不会调用 DeepSeek、发送消息或拨号。

### 3. 验证 DeepSeek 分类

```powershell
.\.runtime\Python312\python.exe -m wx_trade_alert test-classify "买两手 NVDA 150 call"
```

输出末尾应显示：

```text
达到告警阈值：True
```

此步骤会真实调用 DeepSeek API，并可能产生少量 API 费用。

### 4. 在模拟模式观察

确认 `.env` 中仍然是：

```dotenv
DRY_RUN=true
CALLS_ENABLED=false
```

启动监控：

```powershell
.\run.ps1
```

让目标成员发送几条测试消息，检查终端中的消息接收、语音转写和模型判定结果。出现 `DRY-RUN：本应向……发送` 表示告警链路已经运行，但没有真实联系任何人。

按 `Ctrl+C` 停止程序。

### 5. 测试真实文字告警

将 `.env` 改为：

```dotenv
DRY_RUN=false
CALLS_ENABLED=false
```

然后执行：

```powershell
.\.runtime\Python312\python.exe -m wx_trade_alert test-alert
```

接警联系人应该收到一条明确标记为“系统测试”的微信消息，此时不会真实拨号。

### 6. 测试真实语音呼叫

确认文字告警正常后，将 `.env` 改为：

```dotenv
DRY_RUN=false
CALLS_ENABLED=true
```

再显式执行：

```powershell
.\.runtime\Python312\python.exe -m wx_trade_alert test-alert --call
```

此命令会真实发送测试消息并发起微信语音通话。

## 七、正式运行

所有测试通过后运行：

```powershell
.\run.ps1
```

保持 PowerShell、微信和当前 Windows 用户会话运行。按 `Ctrl+C` 可以安全停止。

另开一个 PowerShell 窗口，可以实时查看是否抓到消息以及模型是否达到告警阈值：

```powershell
cd wx_detect
.\watch.ps1
```

日志中的关键内容包括：

- `监控心跳`：每分钟输出一次，表示监听进程仍在正常运行。
- `抓到目标消息`：显示消息类型、发送者和文本摘要。
- `模型判定`：显示 `confidence`、`threshold` 和 `should_alert`。
- `should_alert=True`：达到阈值并进入告警流程。
- `告警消息发送结果` 和 `呼叫第 N 次`：显示真实告警执行结果。

按 `Ctrl+C` 只会结束日志查看，不会停止在另一个窗口运行的监控。

### 本次启动的会话 JSON

每次运行 `.\run.ps1`，程序都会在下面的目录新建一个文件：

```text
data/sessions/YYYY-MM-DD_HH-mm-ss.json
```

文件包含本次启动时间、群名、被监听成员，以及每条消息的微信时间、类型、发送者和正文。语音消息保存本地转写后的文字。例如：

```json
{
  "session_started_at": "2026-09-18T16:50:30+08:00",
  "group_name": "多空双杀华尔街",
  "target_member": "华尔街之狼",
  "latest_message_key": "45374963958@chatroom:71:1789720683000",
  "messages": [
    {
      "message_type": "文本",
      "spoken_at": "2026-09-18T16:38:03+08:00",
      "text": "我走了一半儿，我走了一半儿。"
    }
  ]
}
```

新消息会先原子写入该文件，再把完整 JSON 交给 DeepSeek。模型使用全部历史理解上下文，但只判断 `latest_message_key` 指向的最新消息。程序重启会创建新文件，不会把上一次运行的消息带入新会话。

常用运行参数：

| 配置 | 默认值 | 说明 |
| --- | ---: | --- |
| `ALERT_CONFIDENCE_THRESHOLD` | `0.70` | 触发告警所需的最低置信度 |
| `DEDUPE_MINUTES` | `10` | 相同交易动作的去重时间 |
| `CALLS_PER_HOUR` | `5` | 每小时最多尝试的呼叫次数 |
| `CALL_MAX_ATTEMPTS` | `2` | 一次告警呼叫失败后的最大尝试次数 |
| `CALL_RETRY_SECONDS` | `60` | 呼叫失败后的等待时间 |

长期运行时可以使用 Windows 任务计划程序设置“用户登录后”启动 `run.ps1`。必须选择“仅当用户登录时运行”，不要选择“无论用户是否登录都运行”，否则微信界面发送和呼叫不可用。

## 常见问题

### 提示“未找到微信主窗口”

确认微信已经启动并登录，Windows 没有锁屏，并且微信和项目运行在同一个 Windows 用户会话中。

### 群、成员或联系人匹配到 0 个

检查 `.env` 中的名称是否与微信里显示的名称完全一致。修改后重新运行 `doctor.ps1`。

### 匹配到多个群、成员或联系人

为联系人设置唯一备注；如果存在同名群，建议修改群名，使其能够唯一匹配。

### 模型下载中断

保持网络畅通，再次执行“提前下载模型”的命令。Faster-Whisper 会复用已经下载的缓存。以 `.incomplete` 结尾的文件表示下载尚未完成。

### 语音转写很慢

CPU 模式首次加载模型需要一些时间。可以把 `WHISPER_MODEL` 改为 `base` 降低资源占用，或在正确配置 CUDA 后使用 NVIDIA GPU。

### 换微信账号或迁移到另一台电脑

停止程序，登录新的微信账号，修改 `.env` 中的群、成员和接警联系人，然后依次重新运行 `doctor.ps1`、`probe.ps1` 和各项测试。不要从旧环境复制 `.env`、`data/state.db` 或 `data/listener_watermark.json`。

## 数据和隐私

- DeepSeek 会接收本次启动以来目标成员的完整会话 JSON，不上传其他群成员的普通消息。
- 会话越长，每次请求发送的上下文越多，API 用量和响应时间也会逐渐增加；重启程序会开始一个新会话。
- 语音先在本机转写，DeepSeek 接收的是转写后的文本。
- 运行状态保存在 `data/state.db`。
- 监听进度保存在 `data/listener_watermark.json`。
- 本次启动的目标成员消息保存在 `data/sessions/*.json`。
- 下载的语音保存在 `data/audio/`。
- `.env`、运行数据库、会话 JSON、音频、模型和日志均被 Git 忽略。

## 开发与测试

```powershell
.\.runtime\Python312\python.exe -m pip install -r requirements-dev.txt
.\.runtime\Python312\python.exe -m pytest
```

## 项目结构

```text
wx_trade_alert/
  cli.py             命令行入口
  config.py          .env 配置加载与校验
  detector.py        DeepSeek 交易信号分类
  models.py          消息与交易信号模型
  session_log.py     本次启动的增量会话 JSON
  service.py         监听、处理、告警主流程
  speech.py          SILK 解码和 Faster-Whisper 转写
  state.py           SQLite 队列、上下文和去重状态
  wechat_adapter.py  微信数据库、消息发送和语音呼叫适配
tests/               单元测试
setup.ps1            安装便携 Python 和依赖
doctor.ps1           只读环境检查
probe.ps1            只读实时消息探针
run.ps1              启动监控
watch.ps1            实时查看监控日志
```
