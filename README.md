# DYFetcher - 抖音直播间弹幕抓取系统

一个基于 Flask 和 WebSocket 的抖音直播间实时弹幕抓取系统，支持多直播间并发监控和数据采集。

## 功能特性

- 🔴 **实时弹幕抓取**：通过 WebSocket 连接抖音直播间，实时接收弹幕消息
- 💬 **多类型消息支持**：聊天、礼物、点赞、进场、关注、粉丝团等多种消息类型
- 🏠 **多直播间并发**：支持同时监控多个直播间，可配置最大并发数
- 🌐 **Web API 接口**：提供 RESTful API，方便前端集成和二次开发
- 🔄 **自动保活机制**：心跳包维持连接，自动重连和错误处理
- 📊 **环形缓冲区**：内存优化设计，支持多人同时拉取互不影响
- 🛡️ **速率限制**：IP 级别的启动频率限制，防止滥用
- 🧹 **自动清理**：长时间无活动的直播间自动停止，节省资源

## 项目结构

```
dyfetcher/
├── main.py                 # Flask Web 服务器主程序
├── liveMan.py             # 抖音直播间弹幕抓取核心逻辑
├── ac_signature.py        # 抖音签名算法实现
├── sign.js                # JavaScript 签名脚本
├── sign_v0.js             # 备用签名脚本 v0
├── a_bogus.js             # A-Bogus 参数生成脚本
├── webmssdk.js            # Web SDK 相关脚本
├── requirements.txt       # Python 依赖包
├── Procfile              # Heroku/Gunicorn 部署配置
├── .gitignore            # Git 忽略配置
├── protobuf/             # Protocol Buffers 相关文件
│   ├── __init__.py
│   ├── douyin.proto      # 抖音消息协议定义
│   └── douyin.py         # 生成的 Python 代码
└── templates/            # HTML 模板
    └── index.html        # 前端页面
```

## 环境要求

- Python 3.8+
- Node.js (用于执行 JavaScript 签名脚本)
- Windows / Linux / macOS

## 安装步骤

### 1. 克隆项目

```bash
git clone <repository-url>
cd dyfetcher
```

### 2. 创建虚拟环境（推荐）

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 安装 Node.js 依赖（如需要）

确保已安装 Node.js，某些 JS 引擎可能需要额外的 npm 包。

## 使用方法

### 方式一：直接运行

```bash
python main.py
```

服务将在 `http://localhost:5000` 启动。

### 方式二：使用 Gunicorn（生产环境）

```bash
gunicorn -w 4 -b 0.0.0.0:5000 main:app
```

### 方式三：自定义端口

```bash
# Windows (PowerShell)
$env:PORT=8080; python main.py

# Linux/Mac
PORT=8080 python main.py
```

## API 接口文档

### 1. 首页

```
GET /
```

访问前端页面。

### 2. 启动直播间

```
POST /api/start
Content-Type: application/json

{
  "live_id": "261378947940"
}
```

**参数说明：**
- `live_id`: 直播间号（数字字符串），支持以下格式：
  - 单个字符串：`"261378947940"`
  - 数组：`["261378947940", "123456789"]`
  - 逗号分隔：`"261378947940,123456789"`

**响应示例：**

```json
{
  "status": "ok",
  "started": ["261378947940"],
  "errors": {}
}
```

### 3. 获取弹幕列表

```
GET /api/comments?live_id=261378947940&cursor=0&limit=200
```

**参数说明：**
- `live_id`: 直播间号
- `cursor`: 上次获取的最大消息 ID（首次请求传 0）
- `limit`: 单次返回条数（默认 200，最大 1000）

**响应示例：**

```json
{
  "comments": [
    {
      "id": 1,
      "type": "chat",
      "user_id": "123456",
      "user_name": "用户昵称",
      "content": "你好",
      "timestamp": "2026-03-03 12:00:00"
    }
  ],
  "next_cursor": 1,
  "dropped": false
}
```

**消息类型：**
- `chat`: 聊天消息
- `gift`: 礼物消息
- `like`: 点赞消息
- `enter`: 进入直播间
- `follow`: 关注主播
- `stats`: 直播间统计
- `fansclub`: 粉丝团消息
- `emoji`: 表情包
- `room`: 直播间信息
- `room_stats`: 直播间统计信息

### 4. 停止直播间

```
POST /api/stop
Content-Type: application/json

{
  "live_id": "261378947940"
}
```

## 环境变量配置

可通过环境变量调整系统参数：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `PORT` | 5000 | Web 服务端口 |
| `MAX_ACTIVE_ROOMS` | 30 | 最大同时活跃的直播间数量 |
| `ROOM_IDLE_SECONDS` | 600 | 直播间无活动多少秒后自动停止（10 分钟） |
| `STARTS_PER_MINUTE_PER_IP` | 10 | 每个 IP 每分钟最多启动次数 |
| `MAX_IDS_PER_START` | 10 | 单次请求最多启动的直播间数量 |

**设置示例：**

```bash
# Windows (PowerShell)
$env:MAX_ACTIVE_ROOMS=50
$env:PORT=8080
python main.py

# Linux/Mac
export MAX_ACTIVE_ROOMS=50
export PORT=8080
python main.py
```

## 部署到云平台

### Heroku / Render 等

项目已包含 `Procfile`，可直接部署：

```bash
# 安装 Heroku CLI
heroku create your-app-name
git push heroku main
heroku config set MAX_ACTIVE_ROOMS=50
```

## 开发说明

### 添加新的消息类型处理

在 `liveMan.py` 中的 `_wsOnMessage` 方法中添加新的消息类型映射：

```python
'WebcastYourMessageType': self._parseYourMsg,
```

然后实现对应的解析方法：

```python
def _parseYourMsg(self, payload):
    message = YourMessage().parse(payload)
    # 处理逻辑
    self._append_comment("your_type", content="...")
```

### 修改签名算法

如果抖音更新了签名算法，可以：
1. 更新 `sign.js` 或 `sign_v0.js` 中的 JS 代码
2. 修改 `liveMan.py` 中 `generateSignature` 函数的调用逻辑

## 注意事项

⚠️ **重要提示：**

1. **合法使用**：本项目仅供学习交流使用，请遵守相关法律法规和抖音平台规则
2. **频率限制**：内置了速率限制机制，避免对抖音服务器造成过大压力
3. **资源消耗**：每个直播间会占用独立的 WebSocket 连接和资源，注意合理配置最大并发数
4. **签名时效性**：抖音的签名算法可能会更新，如出现失效请及时更新 JS 脚本
5. **网络环境**：需要能够访问抖音的 WebSocket 服务器（webcast*.douyin.com）

## 常见问题

### Q: 启动时报错 "无效的直播间号"
A: 检查直播间号是否正确，确保该直播间正在直播中。

### Q: WebSocket 连接失败
A: 检查网络连接，确认能正常访问抖音网站，查看防火墙设置。

### Q: 签名计算失败
A: 可能是 Node.js 环境问题或 JS 脚本过时，尝试重新安装依赖或更新签名脚本。

### Q: 如何获取更多类型的消息？
A: 在 `liveMan.py` 中查看 `_wsOnMessage` 方法，根据需要添加新的消息类型解析。

## 技术栈

- **后端框架**: Flask 3.0.3
- **HTTP 客户端**: requests 2.32.4
- **WebSocket**: websocket-client 1.7.0
- **ProtoBuf**: betterproto 2.0.0b6
- **JS 引擎**: PyExecJS 1.5.1 / mini_racer 0.12.4
- **WSGI 服务器**: gunicorn 22.0.0

## License

MIT License

## 致谢

感谢所有为此项目做出贡献的开发者！

---

**免责声明**：本项目仅供学习和研究使用，请勿用于商业目的或任何可能违反法律法规的场景。使用本项目造成的任何后果由使用者自行承担。
