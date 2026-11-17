#!/usr/bin/env python3
"""投稿キューのフォルダ（Instagram/動画・投稿文・カバー・_予約表.md）から、自動投稿用の予約表を作る。

  python scripts/build_queue.py <Instagramフォルダ> --year 2026 [--from 11-18T20:15]

- _予約表.md の表で「予約」欄が ☐ の行だけを取り込む（✔ は Business Suite で予約済みなので除外）
- 動画は docs/media/<ID>.mp4、カバーは docs/media/<ID>.jpg（PNGをJPEGに変換）に置く
- 投稿文は queue/captions/<ID>.txt に置く
- queue/queue.csv に追記する（同じIDは上書き）
ファイル名に日本語を使うとURLで扱いにくいので、IDは英数字にしている。
"""
import argparse
import csv
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "docs" / "media"
CAPTIONS = ROOT / "queue" / "captions"
QUEUE = ROOT / "queue" / "queue.csv"
FIELDS = ["id", "publish_at", "video", "cover", "caption", "title"]


def make_id(year, name, hhmm):
    m = re.match(r"(\d\d)-(\d\d)_(①|②)[^_]*_(.+)$", name)
    mm, dd, kind, rest = m.groups()
    code = rest.split("_")[0]
    kind = "type" if kind == "①" else "list"
    return f"{year}{mm}{dd}-{hhmm.replace(':', '')}-{kind}-{code}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--year", default="2026")
    ap.add_argument("--from", dest="start", help="この日時以降だけ取り込む 例 11-18T20:15")
    a = ap.parse_args()
    src = Path(a.folder)
    MEDIA.mkdir(parents=True, exist_ok=True)
    CAPTIONS.mkdir(parents=True, exist_ok=True)

    existing = {}
    if QUEUE.exists():
        with QUEUE.open(encoding="utf-8") as f:
            existing = {r["id"]: r for r in csv.DictReader(f)}

    table = (src / "_予約表.md").read_text(encoding="utf-8")
    added = 0
    for line in table.splitlines():
        m = re.match(r"\|\s*(\d\d-\d\d)\s*\|\s*(\d\d:\d\d)\s*\|\s*(\S+)\s*\|\s*(☐|✔)\s*\|", line)
        if not m:
            continue
        md, hm, name, mark = m.groups()
        if mark != "☐":
            continue
        if a.start and f"{md}T{hm}" < a.start:
            continue
        pid = make_id(a.year, name, hm)
        shutil.copyfile(src / "動画" / f"{name}.mp4", MEDIA / f"{pid}.mp4")
        cover = ""
        png = src / "カバー" / f"{name}.png"
        if png.exists():
            try:
                from PIL import Image
                Image.open(png).convert("RGB").save(MEDIA / f"{pid}.jpg", quality=90)
                cover = f"{pid}.jpg"
            except ImportError:
                print("Pillow が無いのでカバーは付けません（pip install pillow で付けられます）")
        shutil.copyfile(src / "投稿文" / f"{name}.txt", CAPTIONS / f"{pid}.txt")
        existing[pid] = {"id": pid, "publish_at": f"{a.year}-{md}T{hm}:00+09:00",
                         "video": f"{pid}.mp4", "cover": cover, "caption": f"{pid}.txt",
                         "title": name}
        added += 1

    rows = sorted(existing.values(), key=lambda r: r["publish_at"])
    with QUEUE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{added} 本を取り込みました（予約表の合計 {len(rows)} 本）")


if __name__ == "__main__":
    main()
