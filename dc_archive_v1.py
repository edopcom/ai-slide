# -*- coding: utf-8 -*-
"""
dc_archive v1 - 디시인사이드 마이너 갤러리 저부하 아카이버
  - 게시글 목록 / 본문 수집 (SQLite 저장, 중단 후 이어받기)
  - 저장된 데이터 키워드 검색 및 분석용 Markdown 내보내기

사용법
  python dc_archive_v1.py crawl                 # 전체 수집 (중단 후 다시 실행하면 이어서 진행)
  python dc_archive_v1.py crawl --update        # 새 글만 추가 수집
  python dc_archive_v1.py stats                 # 수집 현황
  python dc_archive_v1.py search 키워드 [키워드2 ...]
  python dc_archive_v1.py export 키워드 [키워드2 ...] --out result.md

필요 패키지: pip install requests beautifulsoup4
"""
import argparse, random, re, sqlite3, sys, time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ───────────────────────── 설정 ─────────────────────────
GALL_ID   = "ho1iday"
BASE      = "https://gall.dcinside.com/mgallery/board"
DB_PATH   = f"{GALL_ID}.db"

DELAY_MIN, DELAY_MAX = 4.0, 8.0      # 요청 간 무작위 대기(초)
LONG_PAUSE_EVERY     = 80            # N회 요청마다
LONG_PAUSE_SEC       = (60, 120)     # 긴 휴식(초)
BACKOFF_START        = 60            # 403/429 발생 시 첫 대기(초)
BACKOFF_MAX          = 1800          # 최대 대기 30분
MAX_CONSEC_FAIL      = 6             # 연속 실패 시 안전 종료

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# ───────────────────────── DB ─────────────────────────
def db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS posts(
        no INTEGER PRIMARY KEY, title TEXT, writer TEXT, date TEXT,
        reply_cnt INTEGER, body TEXT, done INTEGER DEFAULT 0, fetched_at TEXT);
    CREATE TABLE IF NOT EXISTS state(k TEXT PRIMARY KEY, v TEXT);
    """)
    return con

def get_state(con, k, default=None):
    r = con.execute("SELECT v FROM state WHERE k=?", (k,)).fetchone()
    return r[0] if r else default

def set_state(con, k, v):
    con.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (k, str(v)))
    con.commit()

# ───────────────────────── 저부하 요청기 ─────────────────────────
class Polite:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.count = 0
        self.fail = 0
        self.backoff = BACKOFF_START

    def _sleep(self):
        self.count += 1
        if self.count % LONG_PAUSE_EVERY == 0:
            t = random.uniform(*LONG_PAUSE_SEC)
            print(f"  … 긴 휴식 {t:.0f}초 (누적 요청 {self.count})")
            time.sleep(t)
        else:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    def req(self, method, url, **kw):
        while True:
            self._sleep()
            try:
                r = self.s.request(method, url, timeout=20, **kw)
            except requests.RequestException as e:
                r, err = None, str(e)
            if r is not None and r.status_code == 200:
                self.fail, self.backoff = 0, BACKOFF_START
                return r
            self.fail += 1
            code = r.status_code if r is not None else err
            if self.fail >= MAX_CONSEC_FAIL:
                print(f"! 연속 {self.fail}회 실패({code}). 진행 상태 저장 후 종료합니다. 나중에 다시 실행하세요.")
                sys.exit(1)
            wait = self.backoff if (r is not None and r.status_code in (403, 429, 503)) else 30
            print(f"! 요청 실패({code}) → {wait}초 대기 후 재시도")
            time.sleep(wait)
            self.backoff = min(self.backoff * 2, BACKOFF_MAX)

# ───────────────────────── 파싱 ─────────────────────────
def parse_list(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.select("tr.ub-content"):
        num_td = tr.select_one("td.gall_num")
        if not num_td or not num_td.get_text(strip=True).isdigit():
            continue                                   # 공지/설문/광고 제외
        a = tr.select_one("td.gall_tit a")
        w = tr.select_one("td.gall_writer")
        d = tr.select_one("td.gall_date")
        rc = tr.select_one("td.gall_tit .reply_num")
        out.append((
            int(num_td.get_text(strip=True)),
            a.get_text(strip=True) if a else "",
            (w.get("data-nick") or w.get_text(strip=True)) if w else "",
            (d.get("title") or d.get_text(strip=True)) if d else "",
            int(re.sub(r"\D", "", rc.get_text()) or 0) if rc else 0,
        ))
    return out

def parse_view(html):
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("div.write_div")
    return body.get_text("\n", strip=True) if body else ""

# ───────────────────────── 수집 ─────────────────────────
def crawl_lists(con, p, update=False):
    page = 1 if update else int(get_state(con, "list_page", 1))
    empty_streak = 0
    while True:
        r = p.req("GET", f"{BASE}/lists/", params={"id": GALL_ID, "page": page})
        rows = parse_list(r.text)
        if not rows:
            empty_streak += 1
            if empty_streak >= 2:
                print("목록 끝에 도달했습니다.")
                break
        else:
            empty_streak = 0
            before = con.total_changes
            con.executemany("""INSERT OR IGNORE INTO posts(no,title,writer,date,reply_cnt)
                               VALUES(?,?,?,?,?)""", rows)
            new = con.total_changes - before
            con.commit()
            print(f"[목록] page {page}: {len(rows)}건 (신규 {new})")
            if update and new == 0:
                print("새 글이 더 없습니다.")
                break
        page += 1
        if not update:
            set_state(con, "list_page", page)
    if not update:
        set_state(con, "list_done", 1)

def crawl_bodies(con, p):
    todo = [r[0] for r in con.execute(
        "SELECT no FROM posts WHERE done=0 ORDER BY no DESC")]
    print(f"[본문] 남은 글 {len(todo)}건")
    for i, no in enumerate(todo, 1):
        url = f"{BASE}/view/?id={GALL_ID}&no={no}"
        r = p.req("GET", url)
        body = parse_view(r.text)
        con.execute("UPDATE posts SET body=?, done=1, fetched_at=? WHERE no=?",
                    (body, datetime.now().isoformat(timespec="seconds"), no))
        con.commit()
        print(f"  ({i}/{len(todo)}) 글 {no}: 본문 {len(body)}자")

# ───────────────────────── 검색 / 내보내기 ─────────────────────────
def search(con, kws):
    cond = " AND ".join(["(title LIKE ? OR body LIKE ?)"] * len(kws))
    args = [x for k in kws for x in (f"%{k}%", f"%{k}%")]
    return con.execute(f"SELECT no,title,writer,date,body FROM posts WHERE {cond} "
                       f"ORDER BY no DESC", args).fetchall()

def cmd_export(con, kws, out):
    posts = search(con, kws)
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# 검색 결과 v1: {' + '.join(kws)}\n\n")
        f.write(f"- 갤러리: {GALL_ID} / 추출일: {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write(f"- 일치 글 {len(posts)}건\n\n")
        for no, t, w, d, b in posts:
            f.write(f"## [{no}] {t}\n작성자: {w} | {d}\n\n{b or ''}\n\n---\n\n")
    print(f"저장 완료: {out}")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crawl"); c.add_argument("--update", action="store_true")
    sub.add_parser("stats")
    s = sub.add_parser("search"); s.add_argument("kw", nargs="+")
    e = sub.add_parser("export"); e.add_argument("kw", nargs="+"); e.add_argument("--out", default="result.md")
    a = ap.parse_args()
    con = db()

    if a.cmd == "crawl":
        p = Polite()
        if a.update or not get_state(con, "list_done"):
            crawl_lists(con, p, update=a.update)
        crawl_bodies(con, p)
        print("수집 완료")
    elif a.cmd == "stats":
        t, d = con.execute("SELECT COUNT(*), SUM(done) FROM posts").fetchone()
        print(f"글 {t}건 (본문 수집 {d or 0}건), 목록 진행 page {get_state(con,'list_page',1)}")
    elif a.cmd == "search":
        posts = search(con, a.kw)
        for no, t, w, dt, _ in posts:
            print(f"[{no}] {dt} {w} | {t}")
        print(f"\n일치 {len(posts)}건")
    elif a.cmd == "export":
        cmd_export(con, a.kw, a.out)

if __name__ == "__main__":
    main()
