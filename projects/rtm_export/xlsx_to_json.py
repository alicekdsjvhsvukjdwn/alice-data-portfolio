import pandas as pd
import json

xlsx_path = "T1T2T3_anonymized.xlsx"
out_path  = "T1T2T3_anonymized.json"

df = pd.read_excel(xlsx_path)
df = df.fillna("")

data = df.to_dict(orient="records")

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

print("OK:", out_path, "rows:", len(data))
