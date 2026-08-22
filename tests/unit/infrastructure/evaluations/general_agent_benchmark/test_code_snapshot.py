"""真实评测代码快照必须覆盖未提交源码，同时排除展示层噪声。"""

from pathlib import Path

from taichu.infrastructure.evaluations.general_agent_benchmark.code_snapshot import (
    benchmark_code_snapshot_hash,
)


def _seed_snapshot(root: Path) -> None:
    files = {
        "pyproject.toml": "[project]\nname='taichu'\n",
        "uv.lock": "version = 1\n",
        "scripts/run_general_agent_first_live.py": "print('run')\n",
        "scripts/run_general_agent_synthetic_baseline.py": "print('synthetic')\n",
        "src/taichu/runtime.py": "VALUE = 1\n",
        (
            "tests/fixtures/evaluations/general_writing_agent_benchmark/"
            "suite.json"
        ): "{}\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def test_snapshot_hash_tracks_runtime_files_but_ignores_docs(tmp_path: Path) -> None:
    _seed_snapshot(tmp_path)
    initial = benchmark_code_snapshot_hash(tmp_path)

    docs = tmp_path / "docs" / "说明.md"
    docs.parent.mkdir(parents=True)
    docs.write_text("仅展示说明。", encoding="utf-8")
    assert benchmark_code_snapshot_hash(tmp_path) == initial

    runtime = tmp_path / "src" / "taichu" / "runtime.py"
    runtime.write_text("VALUE = 2\n", encoding="utf-8")
    assert benchmark_code_snapshot_hash(tmp_path) != initial
