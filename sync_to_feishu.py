"""
GitHub 中文热门项目榜 - 同步到飞书多维表格

这是一张"历史累积榜":只要曾经上过 Top N,就永久留底,不会被删除。

逻辑:
1. 读取 data.json(今天的 Top N)
2. 用 App ID + App Secret 换取 tenant_access_token
3. 列出表格里所有已有记录,按"项目全名"建立 full_name -> record_id 映射
4. 对今天的每个项目:
   - 之前没记录过 -> 新增一行,打上"首次上榜日期"
   - 之前记录过 -> 更新它的最新状态(排名/Star数/语言/简介/变化类型/上次排名/更新日期),
     但"首次上榜日期"保持不变
5. 不删除任何记录

运行: python sync_to_feishu.py
环境变量:
  FEISHU_APP_ID       飞书自建应用 App ID
  FEISHU_APP_SECRET   飞书自建应用 App Secret
  FEISHU_BASE_TOKEN   多维表格 base_token(默认填了当前这张表,可被环境变量覆盖)
  FEISHU_TABLE_ID     数据表 table_id(默认填了当前这张表,可被环境变量覆盖)
"""
import os
import json
import urllib.request
import urllib.error

API_BASE = "https://open.feishu.cn/open-apis"

DEFAULT_BASE_TOKEN = "KR5Hb4n25aVJD4s7EnFc3QCnnHf"
DEFAULT_TABLE_ID = "tblXCN5xjMU75gRA"


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

APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
BASE_TOKEN = os.environ.get("FEISHU_BASE_TOKEN", DEFAULT_BASE_TOKEN)
TABLE_ID = os.environ.get("FEISHU_TABLE_ID", DEFAULT_TABLE_ID)


def http_request(method, path, body=None, token=None):
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_tenant_access_token():
    resp = http_request(
        "POST",
        "/auth/v3/tenant_access_token/internal",
        {"app_id": APP_ID, "app_secret": APP_SECRET},
    )
    if resp.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {resp}")
    return resp["tenant_access_token"]


def list_existing_records(token):
    """返回 {项目全名: record_id} 映射,用于判断哪些是新项目。"""
    mapping = {}
    page_token = None
    while True:
        path = f"/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records?page_size=100"
        if page_token:
            path += f"&page_token={page_token}"
        resp = http_request("GET", path, token=token)
        if resp.get("code") != 0:
            raise RuntimeError(f"列出记录失败: {resp}")
        items = resp["data"].get("items") or []
        for item in items:
            full_name = item["fields"].get("项目全名")
            if full_name:
                mapping[full_name] = item["record_id"]
        if not resp["data"].get("has_more"):
            break
        page_token = resp["data"].get("page_token")
    return mapping


def common_fields(repo):
    """除"首次上榜日期"外,每次都要刷新的字段。"""
    return {
        "排名": repo["rank"],
        "owner": repo["owner"],
        "项目名": repo["name"],
        "简介": repo.get("description") or "",
        "Star数": repo["stars"],
        "语言": repo.get("language") or "未知",
        "创建日期": repo.get("created_at") or "",
        # 该字段是飞书原生「超链接」类型,CellValue 必须是 {text, link} 对象
        "链接": {"text": repo["full_name"], "link": repo["html_url"]},
        "变化类型": repo.get("change") or "same",
        "上次排名": repo.get("prev_rank"),
    }


def batch_create_records(token, repos, snapshot_date):
    if not repos:
        return
    path = f"/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records/batch_create"
    records = []
    for r in repos:
        fields = {"项目全名": r["full_name"], "首次上榜日期": snapshot_date, "更新日期": snapshot_date}
        fields.update(common_fields(r))
        records.append({"fields": fields})
    resp = http_request("POST", path, {"records": records}, token=token)
    if resp.get("code") != 0:
        raise RuntimeError(f"批量新增失败: {resp}")


def batch_update_records(token, repo_record_pairs, snapshot_date):
    if not repo_record_pairs:
        return
    path = f"/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records/batch_update"
    records = []
    for repo, record_id in repo_record_pairs:
        fields = {"更新日期": snapshot_date}
        fields.update(common_fields(repo))
        records.append({"record_id": record_id, "fields": fields})
    resp = http_request("POST", path, {"records": records}, token=token)
    if resp.get("code") != 0:
        raise RuntimeError(f"批量更新失败: {resp}")


def main():
    if not APP_ID or not APP_SECRET:
        raise SystemExit("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET 环境变量")

    data_path = os.path.join(os.path.dirname(__file__), "data.json")
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    snapshot_date = data["generated_at"][:10]
    repos = data.get("repos", [])

    print("获取 tenant_access_token...")
    token = get_tenant_access_token()

    print("列出已有记录...")
    existing = list_existing_records(token)
    print(f"  历史累计 {len(existing)} 个项目")

    new_repos = []
    update_pairs = []
    for r in repos:
        record_id = existing.get(r["full_name"])
        if record_id:
            update_pairs.append((r, record_id))
        else:
            new_repos.append(r)

    print(f"本次新上榜 {len(new_repos)} 个,已有项目刷新 {len(update_pairs)} 个")

    if new_repos:
        print("写入新项目...")
        batch_create_records(token, new_repos, snapshot_date)

    if update_pairs:
        print("更新已有项目的最新状态...")
        batch_update_records(token, update_pairs, snapshot_date)

    print("完成,没有任何记录被删除。")


if __name__ == "__main__":
    main()
