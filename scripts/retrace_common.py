#!/usr/bin/env python3
"""
retrace_common.py - 共享工具函数
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional

from retrace_paths import find_codex

SCRIPT_DIR = Path(__file__).parent

# 配置
SINGLE_CHUNK_BYTES = 100 * 1024      # 100KB 以下直接处理
MAX_BYTES_PER_CHUNK = 100 * 1024     # 每个分片最大 100KB
MAX_PARALLEL = 20                     # 最大并行数


def find_analysis_command() -> Optional[str]:
    """查找用于 AI 分析的命令。"""
    return find_codex()


def get_data_size(json_str: str) -> int:
    """获取数据字节大小"""
    return len(json_str.encode('utf-8'))


def search(query: str, project: str = None) -> str:
    """执行搜索，返回原始 JSON 字符串"""
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "retrace-search.py"),
        query,
        "--level", "detail",
        "--limit", "0",
        "--json"
    ]
    if project:
        cmd.extend(["--project", project])

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        return "[]"
    return result.stdout or "[]"


def search_all(project: str = None) -> str:
    """获取所有记录，返回原始 JSON 字符串"""
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "retrace-search.py"),
        "--level", "detail",
        "--limit", "0",
        "--json"
    ]
    if project:
        cmd.extend(["--project", project])

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        return "[]"
    return result.stdout or "[]"


def chunk_by_size(results: List[Dict], max_bytes: int = MAX_BYTES_PER_CHUNK) -> List[List[Dict]]:
    """按字节大小自动分片"""
    chunks = []
    current = []
    current_size = 0

    for record in results:
        record_size = len(str(record)) * 2  # 粗略估算

        if current_size + record_size > max_bytes and current:
            chunks.append(current)
            current = []
            current_size = 0

        current.append(record)
        current_size += record_size

    if current:
        chunks.append(current)
    return chunks


def call_analysis_model(data: List[Dict], system_prompt: str, user_prompt: str, timeout: int = 120) -> Dict:
    """调用 Codex exec 分析，返回原始输出。"""
    codex_cmd = find_analysis_command()
    if not codex_cmd:
        return {"success": False, "error": "codex not found"}

    data_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

    import time
    start = time.time()
    try:
        result = subprocess.run(
            [codex_cmd, "exec",
             "--dangerously-bypass-approvals-and-sandbox",
             "--skip-git-repo-check",
             f"{system_prompt}\n\n{user_prompt}\n\nReturn JSON only."],
            input=data_str,
            capture_output=True, text=True, encoding="utf-8", timeout=timeout
        )
        elapsed = time.time() - start

        if result.returncode == 0:
            return {"success": True, "stdout": result.stdout, "elapsed": elapsed}
        return {"success": False, "error": result.stderr[:200], "elapsed": elapsed}
    except Exception as e:
        return {"success": False, "error": str(e), "elapsed": 0}
