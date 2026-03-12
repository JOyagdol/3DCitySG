"""Run benchmark query placeholders."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from citygml_sg.app.pipeline import run_benchmark_pipeline


if __name__ == "__main__":
    raise SystemExit(run_benchmark_pipeline())
