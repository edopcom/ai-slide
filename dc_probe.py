# -*- coding: utf-8 -*-
"""dc_archive_v1.py 검증용: 요청 3번(목록 1, 글 1, 댓글 1)만 보내고 결과를 파일로 저장한다.
실행: pip install requests  →  python dc_probe.py
생성 파일: probe_list.html, probe_view.html, probe_comment.json (이 3개를 전달)
"""
import re, time, requests

GALL_ID = "ho1iday"
H = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
     "Accept-Language": "ko-KR,ko;q=0.9"}
s = requests.Session(); s.headers.update(H)

r = s.get("https://gall.dcinside.com/mgallery/board/lists/",
          params={"id": GALL_ID, "page": 1}, timeout=20)
print("목록", r.status_code, len(r.text))
open("probe_list.html", "w", encoding="utf-8").write(r.text)

# 공지 제외, 댓글이 달린 첫 일반 글 번호 찾기 (없으면 첫 일반 글)
rows = re.findall(r'<tr class="ub-content[^"]*".*?</tr>', r.text, re.S)
pick = None
for tr in rows:
    m = re.search(r'class="gall_num"[^>]*>\s*(\d+)\s*<', tr)
    if not m:
        continue
    no = m.group(1)
    if pick is None:
        pick = no
    if "reply_num" in tr:
        pick = no
        break
print("선택한 글 번호:", pick)
if not pick:
    raise SystemExit("글 번호를 못 찾았습니다. probe_list.html만 전달해 주세요.")

time.sleep(6)
url = f"https://gall.dcinside.com/mgallery/board/view/?id={GALL_ID}&no={pick}"
v = s.get(url, timeout=20)
print("글", v.status_code, len(v.text))
open("probe_view.html", "w", encoding="utf-8").write(v.text)

m = re.search(r'id="e_s_n_o"[^>]*value="([^"]*)"', v.text) or \
    re.search(r'value="([^"]*)"[^>]*id="e_s_n_o"', v.text)
esno = m.group(1) if m else ""
print("e_s_n_o:", "찾음" if esno else "못 찾음")

time.sleep(6)
c = s.post("https://gall.dcinside.com/board/comment/", data={
    "id": GALL_ID, "no": pick, "cmt_id": GALL_ID, "cmt_no": pick,
    "e_s_n_o": esno, "comment_page": 1, "sort": "", "_GALLTYPE_": "M"},
    headers={"X-Requested-With": "XMLHttpRequest", "Referer": url}, timeout=20)
print("댓글", c.status_code, len(c.text))
open("probe_comment.json", "w", encoding="utf-8").write(c.text)
print("완료. probe_list.html / probe_view.html / probe_comment.json 3개를 전달해 주세요.")
