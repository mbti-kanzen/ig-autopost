#!/usr/bin/env python3
"""長期アクセストークン（60日）を更新する。

発行から24時間たったトークンは、切れる前なら更新でき、更新した時点からまた60日使える。
新しいトークンは画面に出さず、引数で指定したファイルに書き出す（GitHub Actions が Secrets に入れ直す）。
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

out = sys.argv[1] if len(sys.argv) > 1 else None
token = os.environ.get("IG_ACCESS_TOKEN")
if not token:
    sys.exit("IG_ACCESS_TOKEN が見つかりません")
url = "https://graph.instagram.com/refresh_access_token?" + urllib.parse.urlencode(
    {"grant_type": "ig_refresh_token", "access_token": token})
try:
    with urllib.request.urlopen(url, timeout=60) as r:
        res = json.loads(r.read().decode())
except urllib.error.HTTPError as e:
    sys.exit(f"更新に失敗: HTTP {e.code} {e.read().decode(errors='replace').replace(token, '***')}")
new = res["access_token"]
days = int(res.get("expires_in", 0)) // 86400
print(f"::add-mask::{new}")
print(f"更新しました。有効期間: あと約{days}日")
if out:
    with open(out, "w", encoding="utf-8") as f:
        f.write(new)
