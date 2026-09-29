# -*- coding: utf-8 -*-
"""검색(제목+내용) / 이미지 구조 확인용: 요청 3번(검색 목록 1, 글 1, 이미지 1)만 보낸다.
실행: python dc_probe2.py
생성 파일: probe2_search.html, probe2_view.html, probe2_imgtags.txt, probe2_image.* (이미지가 있을 때)
"""
import re, time, mimetypes, requests
from urllib.parse import urljoin

GALL_ID = "ho1iday"
KEYWORD = "청음"
H = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
     "Accept-Language": "ko-KR,ko;q=0.9"}
s = requests.Session(); s.headers.update(H)

r = s.get("https://gall.dcinside.com/mgallery/board/lists/",
          params={"id": GALL_ID, "page": 1, "s_type": "search_subject_memo",
                  "s_keyword": KEYWORD}, timeout=20)
print("검색 요청 주소:", r.url)
print("검색", r.status_code, len(r.text))
open("probe2_search.html", "w", encoding="utf-8").write(r.text)

rows = re.findall(r'<tr class="ub-content[^"]*".*?</tr>', r.text, re.S)
nos = []
for tr in rows:
    m = re.search(r'class="gall_num"[^>]*>\s*(\d+)\s*<', tr)
    if m:
        nos.append(m.group(1))
print("검색 결과 글 수(이 페이지):", len(nos), nos[:5])
if not nos:
    raise SystemExit("검색 결과 글을 못 찾았습니다. probe2_search.html만 전달해 주세요.")

# 이미지가 있는 글을 우선 고르되, 목록만으로는 알 수 없어 이미지 아이콘(icon_pic)이 있는 첫 글을 쓴다.
pick = nos[0]
for tr in rows:
    m = re.search(r'class="gall_num"[^>]*>\s*(\d+)\s*<', tr)
    if m and "icon_pic" in tr:
        pick = m.group(1)
        break
print("선택한 글 번호:", pick)

time.sleep(6)
url = f"https://gall.dcinside.com/mgallery/board/view/?id={GALL_ID}&no={pick}"
v = s.get(url, timeout=20)
print("글", v.status_code, len(v.text))
open("probe2_view.html", "w", encoding="utf-8").write(v.text)

m = re.search(r'<div class="write_div".*?(?=<div class="btn_recommend_box|<div class="appending_file_box)',
              v.text, re.S)
seg = m.group(0) if m else v.text
tags = re.findall(r"<img\b[^>]*>", seg)
open("probe2_imgtags.txt", "w", encoding="utf-8").write("\n".join(tags))
print("본문 안 이미지 태그 수:", len(tags))

src = None
for t in tags:
    mm = re.search(r'\b(?:data-original|src)="([^"]+)"', t)
    if mm and mm.group(1).startswith(("http", "//")):
        src = urljoin(url, mm.group(1))
        break
if not src:
    raise SystemExit("본문에서 이미지를 못 찾았습니다. probe2_search.html, probe2_view.html, "
                     "probe2_imgtags.txt를 전달해 주세요.")

time.sleep(6)
i = s.get(src, headers={"Referer": url}, timeout=30)
print("이미지", i.status_code, len(i.content), i.headers.get("Content-Type"))
ext = mimetypes.guess_extension((i.headers.get("Content-Type") or "").split(";")[0]) or ".bin"
open("probe2_image" + ext, "wb").write(i.content)
print("완료. probe2_* 파일 전부를 전달해 주세요.")
