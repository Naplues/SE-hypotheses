from datasets import load_dataset
import json

# 加载 SWE-bench Verified test集
ds = load_dataset("SWE-bench/SWE-bench_Verified", split="test")

out_path = "/data/swe_verified.jsonl"

with open(out_path, "w", encoding="utf-8") as f:
    for sample in ds:
        # 填充mini需要的image镜像名称，和你docker镜像命名保持一致
        sample["image"] = f"sweb.eval.x86_64.{sample['instance_id']}:latest"
        line = json.dumps(sample, ensure_ascii=False)
        f.write(line + "\n")

print(f"✅ jsonl 导出完成：{out_path}")
print(f"总共 {len(ds)} 条任务")

# ========== 额外：单独导出 astropy__astropy-13033 单条jsonl（调试用） ==========
single_sample = [x for x in ds if x["instance_id"] == "astropy__astropy-13033"][0]
single_sample["image"] = f"sweb.eval.x86_64.{single_sample['instance_id']}:latest"
single_out = "/Users/gzq/Repo/FSE2027/single_astropy.jsonl"
with open(single_out, "w", encoding="utf-8") as f:
    f.write(json.dumps(single_sample, ensure_ascii=False)+"\n")
print(f"✅ 单条astropy jsonl：{single_out}")
