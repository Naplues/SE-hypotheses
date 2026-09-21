import json
import os
from pathlib import Path

from datasets import load_dataset

# 国内 HF 镜像加速
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


def export_swebench_verified_repo_urls() -> None:
    ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    out_list = []
    for item in ds:
        repo_short = item["repo"]  # owner/repo
        git_url = f"https://github.com/{repo_short}.git"
        out_list.append(
            {
                "instance_id": item["instance_id"],
                "repo_short": repo_short,
                "git_clone_url": git_url,
                "base_commit": item["base_commit"],
            }
        )
    output = Path(__file__).resolve().parents[2] / "data" / "swebench_verified_repos.json"
    with output.open("w", encoding="utf-8") as handle:
        json.dump(out_list, handle, ensure_ascii=False, indent=2)
    print(f"导出完成，一共 {len(out_list)} 条，文件 {output}")


if __name__ == "__main__":
    export_swebench_verified_repo_urls()
