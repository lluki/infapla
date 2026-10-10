import os
import sys
import json
import time
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Generator, Optional, List, Tuple

logger = logging.getLogger("infapla.sandbox")

SYSTEM_INSTRUCTION = """You are InFaPla (Intelligent Family Planner), an AI companion dedicated to helping a family organize their life.
You have direct read and write access to the family directory.
Key directories and conventions:
- shopping/list.md : The central family shopping list. Uses - [ ] for pending and - [x] ~~item~~ for completed items (at bottom).
- shopping/recipes/<dish-name>.md : Recipes containing ## Info, ## Ingredients, and ## Instructions.
- shopping/mealplan/YYYY-MM-DD.md : Weekly meal plan linking recipes.
- todo/list.md : The family TODO list. Uses - [ ] and completed items at bottom.
- calendar/*.ics : Family calendar events in standard RFC 5545 iCalendar format.
- README.md : Family planner overview.

When asked to update, organize, or add items, use your file editing tools directly to modify the files in the directory.
Always keep Markdown files clean, well-structured, and easy to read.
"""

class SandboxRunner:
    def __init__(
        self,
        data_dir: Path,
        script_path: Optional[Path] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None
    ):
        self.data_dir = Path(data_dir).resolve()
        self.model = model or os.environ.get("AGY_MODEL", "gemini-3.8-flash-low")
        self.effort = effort or os.environ.get("AGY_EFFORT", "low")
        candidate_paths = [
            script_path,
            os.environ.get("INFAPLA_SANDBOX_SCRIPT"),
            shutil.which("run-agy-sandboxed.sh"),
            Path(__file__).resolve().parent / "run-agy-sandboxed.sh",
            Path(__file__).resolve().parent.parent / "run-agy-sandboxed.sh",
        ]
        for p in Path(__file__).resolve().parents:
            candidate_paths.append(p / "share" / "infapla" / "run-agy-sandboxed.sh")
            candidate_paths.append(p / "bin" / "run-agy-sandboxed.sh")

        self.script_path = None
        for cand in candidate_paths:
            if cand and Path(cand).exists():
                self.script_path = Path(cand).resolve()
                break

        if not self.script_path:
            self.script_path = (Path(__file__).resolve().parent.parent / "run-agy-sandboxed.sh").resolve()

    def _get_files_snapshot(self) -> Dict[str, Any]:
        """
        Takes a snapshot of file mtimes and sizes in data_dir to detect changes made by agy.
        """
        snapshot = {}
        for root, dirs, files in os.walk(self.data_dir):
            if ".git" in dirs:
                dirs.remove(".git")
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
                continue
            for f in files:
                full = Path(root) / f
                try:
                    st = full.stat()
                    snapshot[full.relative_to(self.data_dir).as_posix()] = (st.st_mtime_ns, st.st_size)
                except Exception:
                    pass
        return snapshot

    def _detect_modified_files(self, before_snapshot: Dict[str, Any]) -> List[str]:
        after_snapshot = self._get_files_snapshot()
        modified = set()
        for path, meta in after_snapshot.items():
            if path not in before_snapshot or before_snapshot[path] != meta:
                modified.add(path)
        for path in before_snapshot:
            if path not in after_snapshot:
                modified.add(path)
        return sorted(modified)

    def execute_prompt_stream(
        self,
        prompt: str,
        current_file_path: Optional[str] = None,
        file_content: Optional[str] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Runs agy in bubblewrap sandbox via stdio stream-json.
        Yields events:
        - {"type": "chunk", "text": "..."}
        - {"type": "status", "status": "..."}
        - {"type": "done", "response": "...", "files_modified": [...]}
        """
        before_snapshot = self._get_files_snapshot()

        # Build prompt with context if viewing a file
        context_parts = [SYSTEM_INSTRUCTION.strip()]
        if current_file_path:
            context_parts.append(f"\nThe user is currently viewing the file: {current_file_path}")
            if file_content is not None:
                context_parts.append(f"Current content of {current_file_path}:\n```\n{file_content}\n```")
        context_parts.append(f"\nUser query:\n{prompt}")
        full_prompt = "\n\n".join(context_parts)

        # Environment with INFAPLA_DATA_DIR set
        env = os.environ.copy()
        env["INFAPLA_DATA_DIR"] = str(self.data_dir)
        env["WORKSPACE"] = str(self.data_dir)

        cmd = [
            str(self.script_path),
            "--model", self.model,
            "--effort", self.effort,
            "--input-format", "stream-json",
            "--output-format", "stream-json"
        ]

        logger.info(f"Running sandboxed agy in {self.data_dir} for prompt: {prompt[:60]}...")

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1
            )
        except Exception as e:
            logger.error(f"Failed to launch sandboxed agy: {e}")
            yield {"type": "error", "error": f"Failed to start sandbox: {e}"}
            return

        # Send the user message event
        input_payload = json.dumps({"event": "user", "message": {"content": full_prompt}}) + "\n"
        try:
            process.stdin.write(input_payload)
            process.stdin.flush()
            process.stdin.close()
        except Exception as e:
            logger.error(f"Failed to write to agy stdin: {e}")
            yield {"type": "error", "error": f"Failed to write to agent: {e}"}
            try:
                process.kill()
            except Exception:
                pass
            return

        accumulated_text = []

        # Read NDJSON events from stdout
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = data.get("event")

            if event_type == "step_update":
                step = data.get("step_update", {})
                delta = step.get("text_delta")
                if delta:
                    accumulated_text.append(delta)
                    yield {"type": "chunk", "text": delta}

            elif event_type == "result":
                result = data.get("result", {})
                status = result.get("status", "SUCCESS")
                final_response = result.get("response", "".join(accumulated_text))
                error_msg = result.get("error")

                if status == "ERROR":
                    yield {"type": "error", "error": error_msg or "Agent returned an error"}
                else:
                    files_modified = self._detect_modified_files(before_snapshot)
                    yield {
                        "type": "done",
                        "response": final_response,
                        "files_modified": files_modified
                    }
                break

        process.wait()

        # If loop finished without emitting "done"
        if not accumulated_text:
            files_modified = self._detect_modified_files(before_snapshot)
            yield {
                "type": "done",
                "response": "".join(accumulated_text),
                "files_modified": files_modified
            }

    def execute_prompt(
        self,
        prompt: str,
        current_file_path: Optional[str] = None,
        file_content: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synchronous convenience wrapper around execute_prompt_stream.
        """
        full_response = ""
        files_modified = []
        error = None

        for evt in self.execute_prompt_stream(prompt, current_file_path, file_content):
            if evt["type"] == "chunk":
                full_response += evt["text"]
            elif evt["type"] == "done":
                if evt.get("response"):
                    full_response = evt["response"]
                files_modified = evt.get("files_modified", [])
            elif evt["type"] == "error":
                error = evt.get("error")

        return {
            "response": full_response,
            "files_modified": files_modified,
            "error": error
        }
