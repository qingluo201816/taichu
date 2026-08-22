"""为真实评测生成包含未提交源码的确定性代码快照身份。"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)

_SNAPSHOT_FILES = (
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("scripts/run_general_agent_first_live.py"),
    Path("scripts/run_general_agent_synthetic_baseline.py"),
)
_SNAPSHOT_DIRECTORIES = (
    Path("src"),
    Path("tests/fixtures/evaluations/general_writing_agent_benchmark"),
)


def benchmark_code_snapshot_hash(root: Path = Path(".")) -> str:
    """哈希真实运行会消费的源码、依赖锁和固定任务夹具。"""

    resolved_root = root.resolve()
    paths = [
        *(resolved_root / relative for relative in _SNAPSHOT_FILES),
        *(
            path
            for relative in _SNAPSHOT_DIRECTORIES
            for path in (resolved_root / relative).rglob("*")
            if path.is_file()
        ),
    ]
    file_hashes: dict[str, str] = {}
    for path in sorted(paths):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if not path.is_file():
            raise ValueError(f"评测代码快照缺少文件：{path}。")
        relative = path.relative_to(resolved_root).as_posix()
        file_hashes[relative] = sha256(path.read_bytes()).hexdigest()
    if not file_hashes:
        raise ValueError("评测代码快照为空。")
    return canonical_sha256({"files": file_hashes})
