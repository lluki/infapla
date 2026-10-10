import json
import logging
from pathlib import Path
from typing import Optional
from flask import Flask, render_template, request, jsonify, Response, stream_with_context

from .config import Config, default_config
from .daemon import InFaPlaDaemon
from .parsers.shopping import GROUP_CATEGORIES_PROMPT, MERGE_DUPLICATES_PROMPT

logger = logging.getLogger("infapla.server")

def create_app(daemon: InFaPlaDaemon) -> Flask:
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates"
    )
    app.config["JSON_AS_ASCII"] = False
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True

    storage = daemon.storage
    git_mgr = daemon.git_manager
    sandbox = daemon.sandbox

    @app.after_request
    def add_no_cache_headers(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/info", methods=["GET"])
    def get_info():
        return jsonify({
            "model": sandbox.model,
            "effort": sandbox.effort,
            "data_dir": str(storage.data_dir),
            "telegram_active": daemon.telegram.is_configured()
        })

    # File endpoints
    @app.route("/api/files", methods=["GET"])
    def list_files():
        files = storage.list_files()
        return jsonify({"files": files})

    @app.route("/api/file", methods=["GET", "POST"])
    def file_handler():
        if request.method == "GET":
            rel_path = request.args.get("path", "").strip()
            if not rel_path:
                return jsonify({"error": "Path required"}), 400
            try:
                content = storage.read_file(rel_path)
                file_type = storage.classify_file(rel_path)
                history = git_mgr.get_history(limit=5, file_path=rel_path)
                return jsonify({
                    "path": rel_path,
                    "content": content,
                    "type": file_type,
                    "history": history
                })
            except FileNotFoundError:
                return jsonify({"error": "File not found"}), 404
            except PermissionError as pe:
                return jsonify({"error": str(pe)}), 403

        elif request.method == "POST":
            data = request.get_json(force=True) or {}
            rel_path = data.get("path", "").strip()
            content = data.get("content", "")
            if not rel_path:
                return jsonify({"error": "Path required"}), 400
            try:
                storage.write_file(rel_path, content)
                return jsonify({"success": True, "path": rel_path})
            except PermissionError as pe:
                return jsonify({"error": str(pe)}), 403

    @app.route("/api/file/create", methods=["POST"])
    def create_file():
        data = request.get_json(force=True) or {}
        rel_path = data.get("path", "").strip()
        content = data.get("content", "# New File\n")
        if not rel_path:
            return jsonify({"error": "Path required"}), 400
        try:
            storage.write_file(rel_path, content)
            return jsonify({"success": True, "path": rel_path})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/file/delete", methods=["POST"])
    def delete_file():
        data = request.get_json(force=True) or {}
        rel_path = data.get("path", "").strip()
        if not rel_path:
            return jsonify({"error": "Path required"}), 400
        try:
            ok = storage.delete_file(rel_path)
            return jsonify({"success": ok})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    # Git endpoints
    @app.route("/api/git/history", methods=["GET"])
    def git_history():
        file_path = request.args.get("file")
        limit = int(request.args.get("limit", 20))
        commits = git_mgr.get_history(limit=limit, file_path=file_path)
        return jsonify({"commits": commits})

    @app.route("/api/git/diff", methods=["GET"])
    def git_diff():
        commit_hash = request.args.get("commit")
        file_path = request.args.get("file")
        if commit_hash:
            diff_text = git_mgr.get_commit_diff(commit_hash, file_path=file_path)
        else:
            diff_text = git_mgr.get_diff(file_path=file_path)
        return jsonify({"diff": diff_text})

    @app.route("/api/git/last-edited", methods=["GET"])
    def git_last_edited():
        limit = int(request.args.get("limit", 15))
        files = git_mgr.get_last_edited_files(limit=limit)
        return jsonify({"files": files})

    @app.route("/api/git/status", methods=["GET"])
    def git_status():
        st = git_mgr.get_status()
        return jsonify(st)

    @app.route("/api/git/commit", methods=["POST"])
    def git_commit():
        data = request.get_json(force=True) or {}
        msg = data.get("message")
        commit_hash = git_mgr.commit(msg)
        return jsonify({"success": True, "commit": commit_hash})

    @app.route("/api/git/sync", methods=["POST"])
    def git_sync():
        data = request.get_json(force=True) or {}
        msg = data.get("message")
        result = git_mgr.sync(msg)
        return jsonify(result)

    # Specialized: Shopping list
    @app.route("/api/shopping", methods=["GET"])
    def get_shopping():
        try:
            data = storage.get_shopping_data()
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/shopping/toggle", methods=["POST"])
    def toggle_shopping():
        data = request.get_json(force=True) or {}
        item_id = data.get("id") or data.get("text", "")
        if not item_id:
            return jsonify({"error": "Item ID or text required"}), 400
        updated = storage.toggle_shopping(item_id)
        return jsonify(updated)

    @app.route("/api/shopping/add", methods=["POST"])
    def add_shopping():
        data = request.get_json(force=True) or {}
        text = data.get("text", "").strip()
        category = data.get("category")
        if not text:
            return jsonify({"error": "Text required"}), 400
        updated = storage.add_shopping(text, category)
        return jsonify(updated)

    @app.route("/api/shopping/remove", methods=["POST"])
    def remove_shopping():
        data = request.get_json(force=True) or {}
        item_id = data.get("id") or data.get("text", "")
        if not item_id:
            return jsonify({"error": "Item ID or text required"}), 400
        updated = storage.remove_shopping(item_id)
        return jsonify(updated)

    @app.route("/api/shopping/clear-completed", methods=["POST"])
    def clear_shopping_completed():
        updated = storage.clear_shopping_completed()
        return jsonify(updated)

    # Specialized: TODO
    @app.route("/api/todo", methods=["GET"])
    def get_todo():
        try:
            data = storage.get_todo_data()
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/todo/toggle", methods=["POST"])
    def toggle_todo():
        data = request.get_json(force=True) or {}
        item_id = data.get("id") or data.get("text", "")
        if not item_id:
            return jsonify({"error": "Item ID or text required"}), 400
        updated = storage.toggle_todo(item_id)
        return jsonify(updated)

    @app.route("/api/todo/add", methods=["POST"])
    def add_todo():
        data = request.get_json(force=True) or {}
        text = data.get("text", "").strip()
        if not text:
            return jsonify({"error": "Text required"}), 400
        updated = storage.add_todo(text)
        return jsonify(updated)

    @app.route("/api/todo/remove", methods=["POST"])
    def remove_todo():
        data = request.get_json(force=True) or {}
        item_id = data.get("id") or data.get("text", "")
        if not item_id:
            return jsonify({"error": "Item ID or text required"}), 400
        updated = storage.remove_todo(item_id)
        return jsonify(updated)

    # Specialized: Calendar
    @app.route("/api/calendar", methods=["GET"])
    def get_calendar():
        try:
            events = storage.get_calendar_events()
            # Serialize datetimes for JSON
            cleaned = []
            for ev in events:
                item = dict(ev)
                if item.get("dtstart"):
                    item["dtstart"] = item["dtstart"].isoformat()
                if item.get("dtend"):
                    item["dtend"] = item["dtend"].isoformat()
                cleaned.append(item)
            return jsonify({"events": cleaned})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/calendar/add", methods=["POST"])
    def add_calendar():
        import datetime
        data = request.get_json(force=True) or {}
        summary = data.get("summary", "").strip()
        if not summary:
            return jsonify({"error": "Event title required"}), 400
        start_str = data.get("start", "")
        end_str = data.get("end")
        location = data.get("location", "")
        description = data.get("description", "")

        try:
            dtstart = datetime.datetime.fromisoformat(start_str)
        except Exception:
            dtstart = datetime.datetime.now() + datetime.timedelta(days=1)

        dtend = None
        if end_str:
            try:
                dtend = datetime.datetime.fromisoformat(end_str)
            except Exception:
                pass

        filename = storage.add_calendar_event(
            summary=summary,
            dtstart=dtstart,
            dtend=dtend,
            location=location,
            description=description
        )
        return jsonify({"success": True, "file": filename})

    # Specialized: Recipe & Mealplan
    @app.route("/api/recipe", methods=["GET"])
    def get_recipe():
        path = request.args.get("path", "").strip()
        if not path:
            return jsonify({"error": "Path required"}), 400
        try:
            data = storage.get_recipe_data(path)
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/mealplan", methods=["GET"])
    def get_mealplan():
        path = request.args.get("path", "").strip()
        if not path:
            return jsonify({"error": "Path required"}), 400
        try:
            data = storage.get_mealplan_data(path)
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    # AI Chat endpoints
    @app.route("/api/chat", methods=["POST"])
    def chat():
        data = request.get_json(force=True) or {}
        prompt = data.get("prompt", "").strip()
        file_path = data.get("file_path")
        file_content = data.get("file_content")
        stream_mode = data.get("stream", True)

        if not prompt:
            return jsonify({"error": "Prompt required"}), 400

        if stream_mode:
            def generate():
                for event in sandbox.execute_prompt_stream(
                    prompt=prompt,
                    current_file_path=file_path,
                    file_content=file_content
                ):
                    yield f"data: {json.dumps(event)}\n\n"
            return Response(stream_with_context(generate()), mimetype="text/event-stream")
        else:
            result = sandbox.execute_prompt(
                prompt=prompt,
                current_file_path=file_path,
                file_content=file_content
            )
            return jsonify(result)

    @app.route("/api/chat/action", methods=["POST"])
    def chat_action():
        data = request.get_json(force=True) or {}
        action = data.get("action", "")

        if action == "group_categories":
            prompt = GROUP_CATEGORIES_PROMPT
            current_path = "shopping/list.md"
        elif action == "merge_duplicates":
            prompt = MERGE_DUPLICATES_PROMPT
            current_path = "shopping/list.md"
        else:
            return jsonify({"error": f"Unknown action: {action}"}), 400

        content = storage.read_file(current_path)
        result = sandbox.execute_prompt(
            prompt=prompt,
            current_file_path=current_path,
            file_content=content
        )
        # Re-fetch updated list
        updated_data = storage.get_shopping_data()
        return jsonify({
            "result": result,
            "shopping_data": updated_data
        })

    return app

def run_server(config: Optional[Config] = None) -> None:
    cfg = config or default_config
    daemon = InFaPlaDaemon(cfg)
    daemon.start()
    app = create_app(daemon)
    try:
        logger.info(f"Serving InFaPla web interface on http://{cfg.host}:{cfg.port}")
        app.run(host=cfg.host, port=cfg.port, debug=cfg.debug)
    finally:
        daemon.stop()
