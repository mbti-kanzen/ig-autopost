#!/usr/bin/env python3
"""Instagram リール自動投稿（Instagram API with Instagram Login）

予約表 queue/queue.csv を読み、時刻が来た（または20分以内に来る）投稿を1本だけ処理する。
1. 動画のURL・投稿文・カバーを渡して「入れ物（コンテナ）」を作る
2. 処理が終わる（FINISHED）まで待つ
3. 予約時刻まで待ってから公開する（media_publish）
結果は state/posted.json に記録する。

必要な環境変数:
  IG_ACCESS_TOKEN  長期アクセストークン（GitHubではSecretsに入れる。ローカルでは .env）
任意:
  PUBLIC_BASE_URL  動画を置いた公開URLの先頭（未指定なら GitHub Pages のURLを自動で組み立てる）
  IG_USER_ID       InstagramアカウントのID（EAA…型のトークンのとき使う。既定は @16type_kanzen_manual）
  IG_API_VERSION   既定 v27.0
  LEAD_MINUTES     予約時刻の何分前から準備を始めるか（既定 25）
  LATE_HOURS       予約時刻を何時間過ぎても投稿するか（既定 3。過ぎたらスキップして記録）

使い方:
  python scripts/post_due.py                 # 通常（GitHub Actions から15分ごと）
  python scripts/post_due.py --dry-run       # 次の1本の入れ物を作って FINISHED まで確認。公開はしない
  python scripts/post_due.py --id <ID> --now # 指定の1本を今すぐ公開（手動テスト用）
  python scripts/post_due.py --check         # トークンとアカウントの確認だけ
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "queue" / "queue.csv"
CAPTIONS = ROOT / "queue" / "captions"
STATE = ROOT / "state" / "posted.json"
API_VERSION = os.environ.get("IG_API_VERSION", "v27.0")
DEFAULT_IG_USER_ID = "17841480920268169"  # @16type_kanzen_manual（秘密ではない公開ID）


def _token():
    # コピー時に混ざりやすい前後の空白・改行・引用符を取り除く
    return os.environ.get("IG_ACCESS_TOKEN", "").strip().strip('"').strip("'")


# EAA… で始まるトークン（Facebookログイン／統合ログイン型）は graph.facebook.com、
# IGAA… で始まるトークン（Instagramログイン型）は graph.instagram.com に送る
IS_FB_TOKEN = _token().startswith("EAA")
BASE = f"https://{'graph.facebook.com' if IS_FB_TOKEN else 'graph.instagram.com'}/{API_VERSION}"


def load_dotenv():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def log(msg):
    print(f"[{datetime.now(JST):%m-%d %H:%M:%S}] {msg}", flush=True)


class ApiError(Exception):
    pass


def call(method, path, params=None):
    token = _token()
    params = dict(params or {})
    params["access_token"] = token
    url = f"{BASE}/{path}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        # トークンがエラー文に出ないように消してから表示する
        body = body.replace(token, "***")
        raise ApiError(f"HTTP {e.code} {path}: {body}") from None


def public_base():
    b = os.environ.get("PUBLIC_BASE_URL", "").strip()
    if b:
        return b.rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo:
        sys.exit("PUBLIC_BASE_URL が未設定です（GitHub以外で動かすときは .env に書いてください）")
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}"


def read_queue():
    with QUEUE.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["at"] = datetime.fromisoformat(r["publish_at"]).astimezone(JST)
    return sorted(rows, key=lambda r: r["at"])


def read_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8") or "{}")
    return {}


def write_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def me():
    if IS_FB_TOKEN:
        uid = os.environ.get("IG_USER_ID", "").strip() or DEFAULT_IG_USER_ID
        r = call("GET", uid, {"fields": "id,username"})
        return {"user_id": r["id"], "username": r.get("username")}
    return call("GET", "me", {"fields": "user_id,username"})


def report_token_expiry():
    """トークンの有効期限をログに出す（EAA型のみ。トークン自体は出さない）。"""
    if not IS_FB_TOKEN:
        log("トークンの有効期限: （IGAA型のため確認対象外。発行から約60日）")
        return
    try:
        d = call("GET", "debug_token", {"input_token": _token()}).get("data", {})
    except ApiError as e:
        log(f"トークンの有効期限: 確認できませんでした（{str(e)[:120]}）")
        return
    exp = d.get("expires_at", 0)
    data_exp = d.get("data_access_expires_at", 0)
    if exp == 0:
        log("トークンの有効期限: 無期限（expires_at=0）")
    else:
        dt = datetime.fromtimestamp(exp, JST)
        days = (dt - datetime.now(JST)).days
        log(f"トークンの有効期限: {dt:%Y-%m-%d} （あと{days}日）")
    if data_exp:
        dt2 = datetime.fromtimestamp(data_exp, JST)
        log(f"データアクセスの期限: {dt2:%Y-%m-%d}")
    log(f"トークンの有効性: is_valid={d.get('is_valid')} type={d.get('type')}")


def create_container(user_id, row):
    base = public_base()
    caption = (CAPTIONS / row["caption"]).read_text(encoding="utf-8").strip()
    params = {
        "media_type": "REELS",
        "video_url": f"{base}/media/{row['video']}",
        "caption": caption,
        "share_to_feed": "true",
    }
    if row.get("cover"):
        params["cover_url"] = f"{base}/media/{row['cover']}"
    log(f"入れ物を作成: {row['id']}  video_url={params['video_url']}")
    return call("POST", f"{user_id}/media", params)["id"]


def wait_finished(container_id, limit_sec=600):
    start = time.time()
    while True:
        st = call("GET", container_id, {"fields": "status_code,status"})
        code = st.get("status_code")
        log(f"  状態: {code}")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise ApiError(f"動画の処理に失敗: {st}")
        if time.time() - start > limit_sec:
            raise ApiError("動画の処理が10分以内に終わりませんでした")
        time.sleep(20)


def publish(user_id, container_id):
    return call("POST", f"{user_id}/media_publish", {"creation_id": container_id})["id"]


def pick(rows, state, now, lead, late):
    """まだ処理していない投稿のうち、いちばん早いものを返す。"""
    for r in rows:
        s = state.get(r["id"], {})
        if s.get("status") in ("published", "skipped_late", "failed"):
            continue
        if r["at"] - lead > now:
            return None  # まだ早い（次の投稿もさらに先）
        if now - r["at"] > late:
            state[r["id"]] = {"status": "skipped_late", "at": now.isoformat(),
                              "note": "予約時刻を大きく過ぎたためスキップ（手動で投稿してください）"}
            log(f"遅れすぎのためスキップ: {r['id']}")
            continue
        return r
    return None


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--id")
    ap.add_argument("--now", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not _token():
        sys.exit("IG_ACCESS_TOKEN が見つかりません")

    who = me()
    user_id = who["user_id"]
    log(f"アカウント確認OK: @{who.get('username')}")
    if a.check:
        lim = call("GET", f"{user_id}/content_publishing_limit", {"fields": "quota_usage,config"})
        log(f"投稿の上限: {lim}")
        report_token_expiry()
        return

    rows = read_queue()
    state = read_state()
    now = datetime.now(JST)
    lead = timedelta(minutes=int(os.environ.get("LEAD_MINUTES", "25")))
    late = timedelta(hours=float(os.environ.get("LATE_HOURS", "3")))

    if a.id:
        row = next((r for r in rows if r["id"] == a.id), None)
        if not row:
            sys.exit(f"予約表に {a.id} がありません")
    elif a.dry_run:
        row = next((r for r in rows if state.get(r["id"], {}).get("status") != "published"
                    and r["at"] > now), None)
    else:
        row = pick(rows, state, now, lead, late)
    if not row:
        log("いま処理する投稿はありません")
        write_state(state)
        return

    log(f"対象: {row['id']}（予約 {row['at']:%m/%d %H:%M}）")
    try:
        cid = create_container(user_id, row)
        wait_finished(cid)
        if a.dry_run:
            log("ドライラン：入れ物の作成と動画の処理まで成功。公開はしていません（入れ物は24時間で自動で消えます）")
            return
        if not a.now:
            wait = (row["at"] - datetime.now(JST)).total_seconds()
            if wait > 0:
                log(f"予約時刻まで {int(wait)} 秒待ちます")
                time.sleep(wait)
        media_id = publish(user_id, cid)
        state[row["id"]] = {"status": "published", "media_id": media_id,
                            "at": datetime.now(JST).isoformat()}
        log(f"公開しました: {row['id']}  media_id={media_id}")
    except ApiError as e:
        s = state.get(row["id"], {})
        tries = s.get("tries", 0) + 1
        state[row["id"]] = {"status": "failed" if tries >= 2 else "retry", "tries": tries,
                            "error": str(e)[:500], "at": datetime.now(JST).isoformat()}
        write_state(state)
        log(f"失敗（{tries}回目）: {e}")
        sys.exit(1)
    finally:
        if not a.dry_run:
            write_state(state)


if __name__ == "__main__":
    main()
