# CNY/IDR 汇率监控 + 钉钉推送

监控人民币对印尼盾汇率，并推送到钉钉群。适用于出行前兑换印尼盾的汇率跟踪。

## 功能

- **实时汇率**：当前 CNY → IDR 汇率（Frankfurter API，免费无需 key）
- **今日最高**：本日内多次运行记录的最高值（需配合定时任务多次执行）
- **一周最高**：近 7 个交易日最高汇率
- **一周均值**：近 7 个交易日平均汇率
- 近 7 日走势与涨跌
- 推送到钉钉群（Markdown 格式）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置钉钉机器人

1. 打开钉钉群 → **设置** → **智能群助手** → **添加机器人**
2. 选择 **自定义** 机器人
3. 设置名称（如「汇率助手」），安全设置选择：
   - **自定义关键词**：勾选并添加 `汇率`（消息需包含该词）
   - 或 **加签**：复制 SEC 开头的密钥，填入下方 `.env`
4. 复制 Webhook 地址

### 3. 配置本地环境

复制 `.env.example` 为 `.env`，填入你的配置：

```bash
cp .env.example .env
```

编辑 `.env`：

```
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=你的token
DINGTALK_SECRET=你的加签密钥   # 未启用加签可留空
```

### 4. 运行

```bash
python main.py
```

成功后会：
- 在终端打印当前汇率
- 向钉钉群发送一条 Markdown 消息

## 定时推送（可选）

### Windows 任务计划程序

1. 打开「任务计划程序」
2. 创建基本任务，触发器选「每天」，如 9:00
3. 操作选「启动程序」：
   - 程序：`python` 或 `python.exe` 的完整路径
   - 参数：`main.py`
   - 起始于：`项目目录完整路径`（如 `D:\Program\JetBrains\PycharmProjects\agent_lab\cny-idr-monitor`）

### Linux / macOS (cron)

```bash
# 每天 9:00 执行
0 9 * * * cd /path/to/cny-idr-monitor && python main.py
```

## 部署到 GitHub（推荐）

像 trip-activity-app 一样，可部署到 GitHub，实现 **push 即生效** 的静态页 + 定时钉钉推送。

### 1. 创建仓库并推送

在 [github.com/new](https://github.com/new) 创建仓库（如 `cny-idr-monitor`），在项目目录执行：

```bash
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/你的用户名/cny-idr-monitor.git
git push -u origin main
```

### 2. 配置钉钉 Secrets（定时推送用）

在仓库 **Settings → Secrets and variables → Actions** 中新增：

| 名称 | 说明 |
|------|------|
| `DINGTALK_WEBHOOK_URL` | 钉钉机器人 Webhook 地址（必填） |
| `DINGTALK_SECRET` | 加签密钥（未启用可留空，或建同名 Secret 填空） |

### 3. 开启 GitHub Pages

在仓库 **Settings → Pages**：
- **Build and deployment** → **Source** 选 **GitHub Actions**

### 4. 验证部署

- **静态展示页**：push 后 1～2 分钟访问 `https://你的用户名.github.io/cny-idr-monitor/`
- **定时推送**：每天北京时间 9:00 自动执行，也可在 **Actions** 标签页手动触发「CNY/IDR 汇率推送」

定时频率可在 `.github/workflows/rate-notify.yml` 中修改 `cron`。

---

## 注意事项

- 钉钉机器人每分钟最多 20 条消息，建议每天推送 1–2 次即可
- 汇率优先来自 [ExchangeRate-API](https://www.exchangerate-api.com/)（通常含当日），备用 [Frankfurter](https://www.frankfurter.app/)（ECB 数据，可能滞后 1 交易日）
- 实际银行/兑换点汇率会有差异，仅供参考
