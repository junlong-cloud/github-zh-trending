"""
GitHub 中文热门项目榜 - 数据抓取脚本

逻辑:
1. 用 GitHub Search API 拉取最近 N 天内创建、按 star 排序的仓库
2. 逐个检查 description / README 是否包含中文字符
3. 取前 TOP_N 个中文项目,写入 data.json 供前端展示

运行: python fetch_data.py
环境变量: GITHUB_TOKEN (可选,但强烈建议设置,否则限流很容易触发)
"""
import os
import re
import json
import time
import base64
import datetime
import urllib.request
import urllib.error

DAYS_WINDOW = 7
TOP_N = 10
MAX_PAGES = 10  # 每页 30 个,最多扫 300 个新仓库找中文项目
PER_PAGE = 30

def _load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
API_BASE = "https://api.github.com"

CJK_PATTERN = re.compile(r'[一-鿿]')


def gh_request(url):
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "github-zh-trending-script")
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"HTTP {e.code} for {url}: {body[:300]}")
        if e.code == 403:
            print("可能触发限流,建议设置 GITHUB_TOKEN 环境变量后重试。")
        raise


def has_chinese(text):
    if not text:
        return False
    return bool(CJK_PATTERN.search(text))


def fetch_readme_text(full_name):
    """拉取仓库 README,返回纯文本（解码失败则返回空串）。"""
    url = f"{API_BASE}/repos/{full_name}/readme"
    try:
        data = gh_request(url)
    except Exception:
        return ""
    content = data.get("content", "")
    if not content:
        return ""
    try:
        return base64.b64decode(content).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def search_new_repos():
    since = (datetime.date.today() - datetime.timedelta(days=DAYS_WINDOW)).isoformat()
    results = []
    for page in range(1, MAX_PAGES + 1):
        query = f"created:>{since}"
        url = (
            f"{API_BASE}/search/repositories?q={urllib.parse.quote(query)}"
            f"&sort=stars&order=desc&per_page={PER_PAGE}&page={page}"
        )
        data = gh_request(url)
        items = data.get("items", [])
        if not items:
            break
        results.extend(items)
        time.sleep(0.5)  # 避免太快触发限流
        if len(results) >= MAX_PAGES * PER_PAGE:
            break
    return results, since


import urllib.parse  # noqa: E402  (放在文件后部以保持上方逻辑清晰)


def main():
    print(f"扫描最近 {DAYS_WINDOW} 天创建、按 star 排序的新仓库...")
    repos, since = search_new_repos()
    print(f"共拉取 {len(repos)} 个候选仓库,开始筛选中文项目...")

    chinese_repos = []
    for repo in repos:
        if len(chinese_repos) >= TOP_N:
            break
        full_name = repo["full_name"]
        description = repo.get("description") or ""

        is_chinese = has_chinese(description)
        if not is_chinese:
            readme_text = fetch_readme_text(full_name)
            is_chinese = has_chinese(readme_text)
            time.sleep(0.3)

        if is_chinese:
            chinese_repos.append(repo)
            print(f"  [{len(chinese_repos)}] {full_name} - {repo['stargazers_count']} stars")

    total_stars = sum(r["stargazers_count"] for r in chinese_repos)
    lang_count = {}
    for r in chinese_repos:
        lang = r.get("language") or "未知"
        lang_count[lang] = lang_count.get(lang, 0) + 1
    top_language = max(lang_count, key=lang_count.get) if lang_count else "未知"

    output = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "since_date": since,
        "days_window": DAYS_WINDOW,
        "total_stars": total_stars,
        "top_language": top_language,
        "repos": [
            {
                "rank": i + 1,
                "full_name": r["full_name"],
                "owner": r["owner"]["login"],
                "name": r["name"],
                "description": r.get("description") or "",
                "stars": r["stargazers_count"],
                "language": r.get("language") or "未知",
                "created_at": r["created_at"][:10],
                "html_url": r["html_url"],
            }
            for i, r in enumerate(chinese_repos)
        ],
    }

    out_path = os.path.join(os.path.dirname(__file__), "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n完成,共 {len(chinese_repos)} 个中文项目,已写入 {out_path}")


if __name__ == "__main__":
    main()
