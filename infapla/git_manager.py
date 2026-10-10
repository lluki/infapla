import os
import subprocess
import threading
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("infapla.git")

class GitManager:
    def __init__(self, repo_dir: Path):
        self.repo_dir = Path(repo_dir).resolve()
        self.lock = threading.RLock()
        self.ensure_repo()

    def _run_git(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        cmd = ["git", "-C", str(self.repo_dir)] + args
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=check
            )
        except subprocess.CalledProcessError as e:
            logger.debug(f"Git command failed: {' '.join(cmd)} - code {e.returncode}: {e.stderr}")
            raise

    def ensure_repo(self) -> None:
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        git_dir = self.repo_dir / ".git"
        if not git_dir.exists():
            logger.info(f"Initializing Git repository in {self.repo_dir}")
            self._run_git(["init"])
            # Set local committer identity if not set
            self._run_git(["config", "user.name", "InFaPla Daemon"])
            self._run_git(["config", "user.email", "daemon@infapla.local"])
            
            # Initial commit if files exist
            if any(self.repo_dir.iterdir()):
                self._run_git(["add", "-A"], check=False)
                self._run_git(["commit", "-m", "Initial commit by InFaPla"], check=False)

    def is_dirty(self) -> bool:
        with self.lock:
            res = self._run_git(["status", "--porcelain"], check=False)
            return bool(res.stdout.strip())

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            res = self._run_git(["status", "--porcelain"], check=False)
            files = []
            for line in res.stdout.splitlines():
                if not line.strip():
                    continue
                status_code = line[:2]
                path = line[3:].strip()
                files.append({"status": status_code.strip(), "path": path})
            return {
                "dirty": len(files) > 0,
                "changed_files": files
            }

    def commit(self, message: Optional[str] = None) -> Optional[str]:
        with self.lock:
            # Check if there is anything to commit
            status = self._run_git(["status", "--porcelain"], check=False)
            if not status.stdout.strip():
                return None

            if not message:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                message = f"InFaPla auto-commit: {timestamp}"

            self._run_git(["add", "-A"])
            res = self._run_git(["commit", "-m", message])
            logger.info(f"Committed changes: {message}")
            
            # Get latest commit hash
            rev = self._run_git(["rev-parse", "HEAD"], check=False)
            return rev.stdout.strip() if rev.returncode == 0 else "committed"

    def get_history(self, limit: int = 20, file_path: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            # Check if there are any commits
            head_check = self._run_git(["rev-parse", "--verify", "HEAD"], check=False)
            if head_check.returncode != 0:
                return []

            args = ["log", f"-n{limit}", "--pretty=format:%H%x00%an%x00%at%x00%s", "--name-only"]
            if file_path:
                args += ["--", file_path]

            res = self._run_git(args, check=False)
            if res.returncode != 0 or not res.stdout.strip():
                return []

            commits = []
            blocks = res.stdout.strip().split("\n\n")
            for block in blocks:
                lines = block.strip().splitlines()
                if not lines:
                    continue
                header = lines[0].split("\x00")
                if len(header) < 4:
                    continue
                commit_hash, author, timestamp, subject = header[0], header[1], header[2], header[3]
                files = [f.strip() for f in lines[1:] if f.strip()]
                commits.append({
                    "hash": commit_hash,
                    "short_hash": commit_hash[:7],
                    "author": author,
                    "timestamp": int(timestamp),
                    "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(timestamp))),
                    "message": subject,
                    "files": files
                })
            return commits

    def get_last_edited_files(self, limit: int = 15) -> List[Dict[str, Any]]:
        with self.lock:
            # 1. Check uncommitted files first
            status = self._run_git(["status", "--porcelain"], check=False)
            dirty_paths = set()
            uncommitted_files = []
            if status.stdout.strip():
                for line in status.stdout.splitlines():
                    path = line[3:].strip()
                    dirty_paths.add(path)
                    full_p = self.repo_dir / path
                    mtime = full_p.stat().st_mtime if full_p.exists() else time.time()
                    uncommitted_files.append({
                        "path": path,
                        "status": "uncommitted",
                        "timestamp": int(mtime),
                        "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
                        "last_message": "Uncommitted changes"
                    })

            # 2. Get files from git log
            args = ["log", "-n50", "--pretty=format:COMMIT%x00%at%x00%s", "--name-only"]
            res = self._run_git(args, check=False)
            seen_paths = set(dirty_paths)
            history_files = []

            if res.returncode == 0 and res.stdout.strip():
                current_time = 0
                current_msg = ""
                for line in res.stdout.strip().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("COMMIT\x00"):
                        parts = line.split("\x00")
                        current_time = int(parts[1]) if len(parts) > 1 else 0
                        current_msg = parts[2] if len(parts) > 2 else ""
                    else:
                        file_path = line
                        if file_path not in seen_paths:
                            seen_paths.add(file_path)
                            full_p = self.repo_dir / file_path
                            if full_p.exists():
                                history_files.append({
                                    "path": file_path,
                                    "status": "committed",
                                    "timestamp": current_time,
                                    "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(current_time)),
                                    "last_message": current_msg
                                })

            combined = uncommitted_files + history_files
            combined.sort(key=lambda x: x["timestamp"], reverse=True)
            return combined[:limit]

    def get_diff(self, file_path: Optional[str] = None) -> str:
        with self.lock:
            args = ["diff", "HEAD"]
            if file_path:
                args += ["--", file_path]
            res = self._run_git(args, check=False)
            return res.stdout

    def get_commit_diff(self, commit_hash: str, file_path: Optional[str] = None) -> str:
        with self.lock:
            args = ["show", "--format=", "-p", commit_hash]
            if file_path:
                args += ["--", file_path]
            res = self._run_git(args, check=False)
            return res.stdout

    def sync(self, message: Optional[str] = None) -> Dict[str, Any]:
        """Commit local uncommitted changes, then pull with merge and push if a remote exists."""
        with self.lock:
            commit_hash = None
            if self.is_dirty():
                commit_hash = self.commit(message or "Sync changes")

            # Check if any remote is configured
            remotes_res = self._run_git(["remote"], check=False)
            has_remote = bool(remotes_res.stdout.strip())
            pull_output = ""
            push_output = ""

            if has_remote:
                pull_res = self._run_git(["pull", "--no-rebase"], check=False)
                pull_output = pull_res.stdout + pull_res.stderr
                push_res = self._run_git(["push"], check=False)
                push_output = push_res.stdout + push_res.stderr

            return {
                "success": True,
                "committed": bool(commit_hash),
                "commit_hash": commit_hash,
                "has_remote": has_remote,
                "pull_output": pull_output,
                "push_output": push_output,
                "message": "Committed and synced successfully" if has_remote else (
                    "Committed changes (no remote configured to push/pull)" if commit_hash else "No uncommitted changes (no remote configured)"
                )
            }

class PeriodicCommitter:
    def __init__(self, git_mgr: GitManager, interval_seconds: int = 30):
        self.git_mgr = git_mgr
        self.interval = interval_seconds
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="infapla-git-committer")
        self.thread.start()
        logger.info(f"Periodic git committer started (interval={self.interval}s)")

    def stop(self) -> None:
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def _run_loop(self) -> None:
        while self.running:
            time.sleep(self.interval)
            if not self.running:
                break
            try:
                if self.git_mgr.is_dirty():
                    self.git_mgr.commit()
            except Exception as e:
                logger.error(f"Error in periodic git commit: {e}")
