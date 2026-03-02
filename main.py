
import threading

from flask import Flask, jsonify, render_template, request

from liveMan import DouyinLiveWebFetcher

app = Flask(__name__, template_folder="templates", static_folder="static")

# 维护直播间连接对象
_rooms = {}
_rooms_lock = threading.Lock()


def _get_or_create_room(live_id: str) -> DouyinLiveWebFetcher:
    """
    获取或创建一个 DouyinLiveWebFetcher 实例，并在后台线程中启动 websocket 连接。
    """
    with _rooms_lock:
        room = _rooms.get(live_id)
        if room is None:
            room = DouyinLiveWebFetcher(live_id)
            t = threading.Thread(target=room.start, daemon=True)
            t.start()
            _rooms[live_id] = room
    return room


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
    live_id = data.get("live_id")

    if not live_id:
        return jsonify({"error": "缺少 live_id 参数"}), 400
    
    # 验证直播间号格式
    if not str(live_id).isdigit():
        return jsonify({"error": f"无效的直播间号：{live_id}，直播间号必须为数字"}), 400

    try:
        # 创建实例并验证直播间是否有效
        room = DouyinLiveWebFetcher(live_id)
        if not room.validate_live_id():
            return jsonify({"error": f"无效的直播间号：{live_id}，请检查直播间是否存在"}), 400
        
        # 验证通过后启动连接
        t = threading.Thread(target=room.start, daemon=True)
        t.start()
        with _rooms_lock:
            _rooms[live_id] = room
        return jsonify({"status": "ok"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/comments", methods=["GET"]
)
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
        return jsonify({"comments": []})

    comments = room.get_comments(clear=True)
    return jsonify({"comments": comments})


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

    if room:
        try:
            room.stop()
        except Exception:
            pass

    return jsonify({"status": "stopped"})


if __name__ == "__main__":
    # 直接运行 main.py 即可启动后端 + 前端页面
    app.run(host="0.0.0.0", port=5000, debug=True)