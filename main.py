#!/usr/bin/env python3
"""
人民币对印尼盾汇率监控，支持钉钉群推送

使用方法：
1. 在钉钉群添加自定义机器人，获取 Webhook 地址
2. 配置 .env 中的 DINGTALK_WEBHOOK_URL（如启用加签则配置 DINGTALK_SECRET）
3. 运行 python main.py 获取当前汇率并推送
4. 可配合 cron/任务计划程序定时执行（如每天 9:00）
"""

import os
import json
import time
import hmac
import base64
import hashlib
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests


# 单一数据源 Frankfurter（ECB 欧洲央行参考汇率），保证实时/历史/统计一致
# 使用官方 api.frankfurter.dev + v1 接口（base/symbols 参数）
RATE_API = "https://api.frankfurter.dev/v1/latest?base=CNY&symbols=IDR"
HISTORY_API = "https://api.frankfurter.dev/v1/{from_date}..{to_date}?base=CNY&symbols=IDR"

# 本地记录文件：用于计算「今日最高」（多次运行时的日内最高）
RATE_LOG_FILE = Path(__file__).parent / "rate_log.json"


def _load_rate_log() -> dict:
    """加载本地汇率记录 { "2026-03-09": [2458.25, 2459.0, ...] }"""
    if not RATE_LOG_FILE.exists():
        return {}
    try:
        return json.loads(RATE_LOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_today_rate(today: str, rate: float) -> None:
    """将本次汇率追加到今日记录，用于计算今日最高"""
    log = _load_rate_log()
    log.setdefault(today, []).append(rate)
    RATE_LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def get_today_max(today: str) -> float | None:
    """今日已记录的最高汇率（多次运行后才有意义）"""
    log = _load_rate_log()
    rates = log.get(today, [])
    return max(rates) if rates else None


def fetch_rate() -> dict:
    """获取当前 CNY/IDR 汇率（Frankfurter/ECB）"""
    resp = requests.get(RATE_API, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return {
        "rate": data["rates"]["IDR"],
        "date": data["date"],
    }


def fetch_history(days: int = 30) -> list[dict]:
    """获取最近 N 天的历史汇率"""
    from datetime import timedelta
    end = datetime.now().date()
    start = end - timedelta(days=days)
    url = HISTORY_API.format(from_date=start, to_date=end)
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if "rates" not in data:
        return []
    rows = []
    for d, v in sorted(data["rates"].items()):
        # v 可能是 {"IDR": xxx} 或直接是数字（兼容不同版本）
        rate_val = v.get("IDR", v) if isinstance(v, dict) else v
        rows.append({"date": d, "rate": rate_val})
    return rows


def build_dingtalk_url(webhook: str, secret: str | None) -> str:
    """如启用加签，将 timestamp 和 sign 追加到 URL"""
    if not secret:
        return webhook
    timestamp = str(round(time.time() * 1000))
    sign_str = f"{timestamp}\n{secret}"
    sign_b64 = base64.b64encode(
        hmac.new(
            secret.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    sign_encoded = urllib.parse.quote(sign_b64)
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={timestamp}&sign={sign_encoded}"


def send_to_dingtalk(webhook: str, secret: str | None, title: str, text: str) -> bool:
    """发送 Markdown 消息到钉钉群"""
    url = build_dingtalk_url(webhook, secret)
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": text,
        },
    }
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    if result.get("errcode") != 0:
        raise RuntimeError(f"钉钉返回错误: {result}")
    return True


def format_markdown(
    rate: float,
    date: str,
    today_max: float | None = None,
    week_max: float | None = None,
    week_avg: float | None = None,
    history: list[dict] | None = None,
) -> str:
    """生成钉钉 Markdown 消息内容（优化排版，兼容移动端）"""
    lines = [
        "## 💱 人民币 → 印尼盾",
        "",
        f"**实时**　1 CNY = **{rate:,.2f}** IDR",
        "",
        f"📅 {date}",
        "",
    ]

    # 汇总指标（分行展示，移动端更易读）
    if today_max is not None or week_max is not None or week_avg is not None:
        lines.append("**今日最高**　{0}　　**一周最高**　{1}　　**一周均值**　{2}".format(
            f"{today_max:,.2f}" if today_max is not None else "--",
            f"{week_max:,.2f}" if week_max is not None else "--",
            f"{week_avg:,.2f}" if week_avg is not None else "--",
        ))
        lines.append("")

    if history and len(history) >= 2:
        rates = [r["rate"] for r in history]
        latest = rates[-1]
        prev = rates[-2]
        change = latest - prev
        pct = (change / prev) * 100 if prev else 0
        if change > 0:
            lines.append(f"📈 较昨日　+{change:.2f}　({pct:+.2f}%)")
        else:
            lines.append(f"📉 较昨日　{change:.2f}　({pct:.2f}%)")
        lines.append("")

        # 近 7 日（列表格式，钉钉移动端不支持表格）
        recent = history[-7:] if len(history) >= 7 else history
        lines.append("**近 7 日**")
        for r in recent:
            lines.append(f"- {r['date']}　{r['rate']:,.2f}")

    return "\n".join(lines)


def load_config() -> tuple[str | None, str | None]:
    """从环境变量或 .env 加载配置"""
    webhook = os.environ.get("DINGTALK_WEBHOOK_URL")
    secret = os.environ.get("DINGTALK_SECRET") or None
    if not webhook:
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k == "DINGTALK_WEBHOOK_URL":
                        webhook = v
                    elif k == "DINGTALK_SECRET":
                        secret = v if v else None
    return webhook, secret


def main():
    print("正在获取 CNY/IDR 汇率...")
    rate_data = fetch_rate()
    rate = rate_data["rate"]
    date = rate_data["date"]

    # 记录本次汇率，用于计算今日最高
    today_str = datetime.now().strftime("%Y-%m-%d")
    _save_today_rate(today_str, rate)
    today_max = get_today_max(today_str)

    history = []
    try:
        history = fetch_history(days=7)
    except Exception as e:
        print(f"获取历史汇率失败（不影响推送）: {e}")

    # 一周最高、一周平均
    week_max = max(r["rate"] for r in history) if history else None
    week_avg = sum(r["rate"] for r in history) / len(history) if history else None

    print(f"实时：1 CNY = {rate:,.2f} IDR ({date})")
    if today_max is not None:
        print(f"今日最高：{today_max:,.2f}")
    if week_max is not None:
        print(f"一周最高：{week_max:,.2f}")
    if week_avg is not None:
        print(f"一周均值：{week_avg:,.2f}")

    webhook, secret = load_config()
    if not webhook:
        print("未配置 DINGTALK_WEBHOOK_URL，跳过钉钉推送。")
        print("请在 .env 中设置 DINGTALK_WEBHOOK_URL，或导出环境变量。")
        return

    title = f"CNY/IDR 汇率 {date}：1 CNY ≈ {rate:,.0f} IDR"
    text = format_markdown(
        rate, date,
        today_max=today_max,
        week_max=week_max,
        week_avg=week_avg,
        history=history,
    )

    try:
        send_to_dingtalk(webhook, secret, title, text)
        print("已推送到钉钉群。")
    except Exception as e:
        print(f"钉钉推送失败: {e}")
        raise


if __name__ == "__main__":
    main()
