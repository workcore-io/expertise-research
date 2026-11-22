# 위키를 읽어 대시보드 HTML 한 장을 만든다 (템플릿.html + 화면 기준.css). 위키 파일은 읽기만 한다.
# 실행 (저장소 맨 위 폴더에서, 같은 버전을 다시 만들 때는 -f): python3 tools/만들기.py [버전]   예) python3 tools/만들기.py v1
# 결과: tools/전문성 대시보드_[버전].html
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "example"
WIKI = ROOT / "2 위키"
CHECK = ROOT / "3 확인"
OUT_DIR = Path(__file__).resolve().parent
ARGS = [a for a in sys.argv[1:] if a != "-f"]
FORCE = "-f" in sys.argv
VERSION = ARGS[0] if ARGS else "v1"

FOLDERS = [("1 판단기준", "판단기준"), ("2 경험", "경험"), ("3 개념", "개념"),
           ("4 영향받은 생각", "영향받은 생각"), ("5 원천요약", "원천요약")]

LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
PAREN_RE = re.compile(r"\(([^()]*)\)")
SRC_KEYS = ("인터뷰", "경력기술서", "이력서", "뉴스레터", "상황질문")


def sources_in(paren):
    """괄호 하나 안에서 원천 이름들을 뽑는다."""
    out = []
    if not any(k in paren for k in SRC_KEYS):
        return out
    if "경력기술서" in paren:
        out.append("경력기술서")
    if "이력서" in paren:
        out.append("이력서")
    for n in re.findall(r"뉴스레터\s*(\d)", paren):
        out.append(f"뉴스레터 {n}")
    m = re.search(r"인터뷰(.*)", paren)
    if m:
        for n in re.findall(r"(\d)회", m.group(1)):
            out.append(f"인터뷰 {n}회")
    if "상황질문" in paren:
        out.append("상황질문 1회")
    return out


def parse_page(path, kind):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip()
    meta = {}
    flags = []
    body_start = 1
    if len(lines) > 1 and lines[1].startswith("- 종류:"):
        body_start = 2
        for part in lines[1][2:].split(" · "):
            if ":" in part:
                k, v = part.split(":", 1)
                meta[k.strip()] = v.strip()
            else:
                flags.append(part.strip())
    body = "\n".join(lines[body_start:]).strip("\n")
    sections = {}
    cur = None
    for ln in body.splitlines():
        if ln.startswith("## "):
            cur = ln[3:].strip()
            sections[cur] = []
        elif cur:
            sections[cur].append(ln)
    links = sorted(set(LINK_RE.findall(body)))
    cites = []
    for p in PAREN_RE.findall(body):
        cites += sources_in(p)
    evidence = 0
    if "근거" in sections:
        evidence = sum(1 for l in sections["근거"] if l.strip().startswith("- ") and '"' in l)
    years = None
    m = re.search(r"\((\d{4})-(\d{4})?\)$", title)
    if m:
        years = [int(m.group(1)), int(m.group(2)) if m.group(2) else None]
    status = meta.get("상태", "")
    return {
        "title": title, "kind": kind, "path": str(path.relative_to(ROOT)), "status": status, "flags": flags,
        "updated": meta.get("갱신", ""), "origin": meta.get("원본", ""),
        "body": body, "links": links, "cites": cites, "evidence": evidence,
        "years": years,
        "plain": next((l for l in sections.get("쉽게 말하면", []) if l.strip()), ""),
    }


def source_key(title):
    m = re.match(r"(인터뷰 \d회|뉴스레터 \d)", title)
    if m:
        return m.group(1)
    if title.startswith("경력기술서"):
        return "경력기술서"
    return title


def parse_questions():
    if not (ROOT / "질문.md").exists():  # 공개 예제에는 질문.md가 없다
        return {"head": "", "items": [], "ref": ""}
    text = (ROOT / "질문.md").read_text(encoding="utf-8")
    main, _, ref = text.partition("\n---\n")
    items = []
    for block in re.split(r"\n(?=\d+\. \*\*)", main):
        m = re.match(r"(\d+)\. \*\*(.+?)\*\*\s*\((.+?)\)", block)
        if not m:
            continue
        item = {"no": int(m.group(1)), "title": m.group(2), "type": m.group(3)}
        for key in ("인용", "해석", "답", "본인 답", "반영"):
            mm = re.search(rf"^\s*- {key}: (.+)", block, re.M)
            item[key] = mm.group(1).strip() if mm else ""
        item["reflected"] = bool(item["반영"])
        items.append(item)
    head = main.split("\n")[0].lstrip("# ")
    return {"head": head, "items": items, "ref": ref.strip()}


def parse_log():
    if not (ROOT / "기록.md").exists():  # 공개 예제에는 기록.md가 없다
        return {"interviews": [], "events": []}
    text = (ROOT / "기록.md").read_text(encoding="utf-8")
    interviews, events = [], []
    for ln in text.splitlines():
        m = re.match(r"- (\d{4}-\d{2}-\d{2}) (\d)회, 답한 질문 (.+?), 남은 질문 (\d+)개", ln)
        if m:
            interviews.append({"date": m.group(1), "no": int(m.group(2)),
                               "answered": m.group(3), "left": int(m.group(4))})
            events.append({"date": m.group(1), "kind": "인터뷰", "text": ln[2:]})
            continue
        m = re.match(r"- (위키 반영|확인) (\d{4}-\d{2}-\d{2}), (.+)", ln)
        if m:
            events.append({"date": m.group(2), "kind": m.group(1), "text": m.group(3)})
    return {"interviews": interviews, "events": events}


def parse_checks():
    out = []
    for f in sorted(CHECK.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ")
        date = re.search(r"- 날짜: (.+)", text)
        cases = []
        for blk in re.split(r"\n## ", text)[1:]:
            name, _, rest = blk.partition("\n")
            subs = {}
            for sb in re.split(r"\n### ", "\n" + rest):
                h, _, c = sb.partition("\n")
                subs[h.strip() or "_"] = c.strip()
            cases.append({"name": name.strip(), "situation": subs.get("_", "").strip(),
                          "answer": subs.get("답 요지", ""),
                          "pages": [p.strip() for p in subs.get("근거 쪽", "").split(" · ") if p.strip()],
                          "verdict": subs.get("판정 (원문 그대로)", "")})
        out.append({"title": title, "date": date.group(1) if date else "", "cases": cases})
    return out


def build_html():
    pages = []
    for folder, kind in FOLDERS:
        for f in sorted((WIKI / folder).glob("*.md")):
            pages.append(parse_page(f, kind))

    titles = {p["title"] for p in pages}
    backlinks = {t: [] for t in titles}
    for p in pages:
        for l in p["links"]:
            if l in backlinks and p["title"] not in backlinks[l]:
                backlinks[l].append(p["title"])
    for p in pages:
        p["backlinks"] = sorted(backlinks[p["title"]])

    # 원천별로 인용한 페이지 수
    src_map = {source_key(p["title"]): p["title"] for p in pages if p["kind"] == "원천요약"}
    cite_pages = {k: set() for k in src_map}
    cite_total = {k: 0 for k in src_map}
    for p in pages:
        for c in p["cites"]:
            if c in cite_pages:
                cite_pages[c].add(p["title"])
                cite_total[c] += 1

    data = {
        "built": __import__("datetime").date.today().isoformat(),
        "pages": pages,
        "sourceMap": src_map,
        "citePages": {k: sorted(v) for k, v in cite_pages.items()},
        "citeTotal": cite_total,
        "questions": parse_questions(),
        "log": parse_log(),
        "checks": parse_checks(),
    }

    tpl = (OUT_DIR / "템플릿.html").read_text(encoding="utf-8")
    # 겉모습(색, 글꼴, 사이드바, 카드 등)은 「화면 기준.css」 한 파일이 기준이다. 스타일 맨 끝에 넣어 앞의 규칙을 덮는다.
    base = (OUT_DIR / "화면 기준.css").read_text(encoding="utf-8")
    tpl = tpl.replace("/*__BASE_CSS__*/", base.replace("</", "<\\/"))
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return tpl.replace("/*__DATA__*/null", blob), len(pages)


if __name__ == "__main__":
    out = OUT_DIR / f"전문성 대시보드_{VERSION}.html"
    if out.exists() and not FORCE:
        sys.exit(f"이미 있음: {out.name}. 다른 버전 이름을 주세요 (예: v2).")
    html, n = build_html()
    out.write_text(html, encoding="utf-8")
    print(f"만듦: {out}  (페이지 {n}개)")
