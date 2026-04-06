import os
import threading
import time

from flask import Flask, jsonify, render_template, request

# 注意：请确保 liveMan.py 存在且 DouyinLiveWebFetcher 可正常导入
from liveMan import DouyinLiveWebFetcher

app = Flask(__name__, template_folder="templates", static_folder="static")

# 维护直播间连接对象：key 为 live_id，value 为 DouyinLiveWebFetcher 实例
_rooms: dict[str, DouyinLiveWebFetcher] = {}
_rooms_lock = threading.Lock()
_room_last_access: dict[str, float] = {}

# 公网保护参数（可通过环境变量覆盖）
MAX_ACTIVE_ROOMS = int(os.getenv("MAX_ACTIVE_ROOMS", "50"))
ROOM_IDLE_SECONDS = int(os.getenv("ROOM_IDLE_SECONDS", "600"))  # 10分钟没人拉取就自动停止
STARTS_PER_MINUTE_PER_IP = int(os.getenv("STARTS_PER_MINUTE_PER_IP", "100"))  # 修复：恢复限流常量
MAX_IDS_PER_START = int(os.getenv("MAX_IDS_PER_START", "10"))  # 修复：恢复单次请求上限常量

_ip_start_log: dict[str, list[float]] = {}
_rate_lock = threading.Lock()


def _rate_limit_start(ip: str) -> bool:
    # 修复：补全限流逻辑，不再永远返回True
    now = time.time()
    with _rate_lock:
        lst = _ip_start_log.get(ip, [])
        # 清理超过1分钟的记录
        lst = [t for t in lst if now - t < 60]
        # 判断：超过每分钟启动上限则拦截
        if len(lst) >= STARTS_PER_MINUTE_PER_IP:
            return False
        # 未超限则添加当前时间并放行
        lst.append(now)
        _ip_start_log[ip] = lst
        return True


def _cleanup_rooms_loop():
    while True:
        time.sleep(30)
        now = time.time()
        to_stop: list[str] = []
        with _rooms_lock:
            for lid in list(_rooms.keys()):
                last = _room_last_access.get(lid, now)
                if ROOM_IDLE_SECONDS > 0 and now - last > ROOM_IDLE_SECONDS:
                    to_stop.append(lid)

        for lid in to_stop:
            with _rooms_lock:
                room = _rooms.pop(lid, None)
                _room_last_access.pop(lid, None)
            if room:
                try:
                    room.stop()
                except Exception:
                    pass


def _start_room_thread(live_id: str) -> DouyinLiveWebFetcher:
    """
    为指定直播间启动一个抓取线程（如果还没有的话）。
    线程中调用 DouyinLiveWebFetcher.start()，内部会进行直播间号校验。
    """
    # 第一次检查：若已存在则直接复用；同时校验活跃上限
    with _rooms_lock:
        if len(_rooms) >= MAX_ACTIVE_ROOMS and live_id not in _rooms:
            raise ValueError(f"当前活跃房间数已达上限（{MAX_ACTIVE_ROOMS}），请稍后再试或减少房间数")
        exists = _rooms.get(live_id)
        if exists is not None:
            return exists

    new_room = DouyinLiveWebFetcher(live_id)

    # 在 start() 之前先进行一次显式校验，尽早给前端错误信息
    if not new_room.validate_live_id():
        raise ValueError(f"无效的直播间号：{live_id}，请检查直播间是否存在且正在直播")

    # 双重检查：校验通过后，可能其他并发已插入；此处再确认一次
    with _rooms_lock:
        current = _rooms.get(live_id)
        if current is not None:
            return current
        # 再次校验活跃上限（并发下可能已达上限）
        if len(_rooms) >= MAX_ACTIVE_ROOMS:
            raise ValueError(f"当前活跃房间数已达上限（{MAX_ACTIVE_ROOMS}），请稍后再试或减少房间数")
        # 先放入字典，随后启动线程，避免并发重复创建
        _rooms[live_id] = new_room

    t = threading.Thread(target=new_room.start, daemon=True)
    t.start()

    return new_room


@app.after_request
def _add_no_cache_headers(resp):
    # 对 API 响应禁用缓存，避免 CDN/反代缓存导致前端拿到旧数据
    try:
        p = request.path or ""
        if p.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
    except Exception:
        pass
    return resp


@app.route("/")
def index():
    """前端页面"""
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def api_start():
    """
    根据 live_id 启动或复用一个直播抓取连接。
    """
    data = request.get_json() or {}
    raw = data.get("live_id")

    if not raw:
        return jsonify({"error": "缺少 live_id 参数"}), 400

    xff = request.headers.get("X-Forwarded-For")
    if xff:
        # 只取第一个（最左）IP
        client_ip = xff.split(",")[0].strip()
    else:
        client_ip = request.headers.get("CF-Connecting-IP") or request.remote_addr or "unknown"
    if not _rate_limit_start(client_ip):
        return jsonify({"error": "启动过于频繁，请稍后再试"}), 429

    # 支持：单个字符串 / 字符串数组 / 用逗号、空格分隔的字符串
    live_ids: list[str]
    if isinstance(raw, list):
        live_ids = [str(x).strip() for x in raw if str(x).strip()]
    else:
        txt = str(raw)
        # 兼容中英文逗号、分号、空格
        for sep in ["；", ";"]:
            txt = txt.replace(sep, ",")
        live_ids = [p.strip() for p in txt.replace("，", ",").split(",") if p.strip()]

    if not live_ids:
        return jsonify({"error": "未解析到有效的 live_id"}), 400

    # 修复：恢复单次请求数量限制
    if len(live_ids) > MAX_IDS_PER_START:
        return jsonify({"error": f"单次最多启动 {MAX_IDS_PER_START} 个直播间"}), 400

    started: list[str] = []
    errors: dict[str, str] = {}

    for lid in live_ids:
        if not lid.isdigit():
            errors[lid] = "直播间号必须为数字"
            continue
        try:
            _start_room_thread(lid)
            started.append(lid)
            with _rooms_lock:
                _room_last_access[lid] = time.time()
        except ValueError as e:
            errors[lid] = str(e)
        except Exception as e:
            errors[lid] = f"启动失败：{e}"

    if not started and errors:
        # 全部失败
        return jsonify({"error": "所有直播间启动失败", "detail": errors}), 400

    # 部分或全部成功
    return jsonify({"status": "ok", "started": started, "errors": errors})


# 修复：闭合括号，修正语法错误
@app.route("/api/comments", methods=["GET"])
def api_comments():
    """
    轮询获取某个直播间当前缓存的弹幕列表。
    """
    live_id = request.args.get("live_id")
    if not live_id:
        return jsonify({"error": "缺少 live_id 参数"}), 400

    with _rooms_lock:
        room = _rooms.get(live_id)

    if not room:
        # 还未启动此直播间
        return jsonify({"comments": [], "next_cursor": 0, "dropped": False})

    cursor = request.args.get("cursor", "0")
    limit = request.args.get("limit", "200")
    try:
        cursor_i = int(cursor)
    except Exception:
        cursor_i = 0
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 200

    comments, next_cursor, dropped = room.get_comments_since(cursor=cursor_i, limit=limit_i)

    with _rooms_lock:
        _room_last_access[live_id] = time.time()

    return jsonify({"comments": comments, "next_cursor": next_cursor, "dropped": dropped})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """
    主动关闭某个直播间连接（可选）。
    """
    data = request.get_json() or {}
    live_id = data.get("live_id")

    if not live_id:
        return jsonify({"error": "缺少 live_id 参数"}), 400

    with _rooms_lock:
        room = _rooms.pop(live_id, None)
        _room_last_access.pop(live_id, None)

    if room:
        try:
            room.stop()
        except Exception:
            pass

    return jsonify({"status": "stopped"})


@app.route("/api/room_stats", methods=["GET"])
def api_room_stats():
    """
    诊断用：查看直播间缓冲与游标信息，帮助排查“已连接但无弹幕”的问题。
    """
    live_id = request.args.get("live_id")
    if not live_id:
        return jsonify({"error": "缺少 live_id 参数"}), 400

    with _rooms_lock:
        room = _rooms.get(live_id)
    if not room:
        return jsonify({"exists": False, "message": "房间未启动"})

    # 读取内部缓冲的基本信息
    try:
        with room._comments_lock:  # noqa: SLF001  直接读取内部状态用于诊断
            buf = room._comments
            size = len(buf)
            oldest_id = buf[0]["id"] if size else 0
            newest_id = buf[-1]["id"] if size else 0
        return jsonify({
            "exists": True,
            "buffer_size": size,
            "oldest_id": oldest_id,
            "newest_id": newest_id,
        })
    except Exception as e:
        return jsonify({"exists": True, "error": f"读取缓冲失败：{e}"}), 500


if __name__ == "__main__":
    # 直接运行 main.py 即可启动后端 + 前端页面
    port = int(os.getenv("PORT", "5000"))
    threading.Thread(target=_cleanup_rooms_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False)