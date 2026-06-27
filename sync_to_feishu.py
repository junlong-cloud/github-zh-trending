"""
GitHub 中文热门项目榜 - 同步到飞书多维表格

逻辑:
1. 读取 data.json
2. 用 App ID + App Secret 换取 tenant_access_token
3. 清空表格里的旧记录
4. 把当前 Top N 批量写入(全量替换,语义上等价于"每日快照覆盖")

运行: python sync_to_feishu.py
环境变量:
  FEISHU_APP_ID       飞书自建应用 App ID
  FEISHU_APP_SECRET   飞书自建应用 App Secret
  FEISHU_BASE_TOKEN   多维表格 base_token(默认填了当前这张表,可被环境变量覆盖)
  FEISHU_TABLE_ID     数据表 table_id(默认填了当前这张表,可被环境变量覆盖)
"""
import os
import json
import time
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


def list_all_record_ids(token):
    record_ids = []
    page_token = None
    while True:
        path = f"/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records?page_size=100"
        if page_token:
            path += f"&page_token={page_token}"
        resp = http_request("GET", path, token=token)
        if resp.get("code") != 0:
            raise RuntimeError(f"列出记录失败: {resp}")
        items = resp["data"].get("items") or []
        record_ids.extend(item["record_id"] for item in items)
        if not resp["data"].get("has_more"):
            break
        page_token = resp["data"].get("page_token")
    return record_ids


def batch_delete_records(token, record_ids):
    if not record_ids:
        return
    # 单批最多 500,这里数据量小,一次就够
    path = f"/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records/batch_delete"
    resp = http_request("POST", path, {"records": record_ids}, token=token)
    if resp.get("code") != 0:
        raise RuntimeError(f"批量删除失败: {resp}")


def build_record_fields(repo, snapshot_date):
    return {
        "排名": repo["rank"],
        "项目全名": repo["full_name"],
        "owner": repo["owner"],
        "项目名": repo["name"],
        "简介": repo.get("description") or "",
        "Star数": repo["stars"],
        "语言": repo.get("language") or "未知",
        "创建日期": repo.get("created_at") or "",
        # 该字段被识别为飞书原生「超链接」类型,CellValue 必须是 {text, link} 对象,纯字符串会报 URLFieldConvFail
        "链接": {"text": repo["full_name"], "link": repo["html_url"]},
        "变化类型": repo.get("change") or "same",
        "上次排名": repo.get("prev_rank"),
        "更新日期": snapshot_date,
    }


def batch_create_records(token, repos, snapshot_date):
    if not repos:
        return
    path = f"/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records/batch_create"
    records = [{"fields": build_record_fields(r, snapshot_date)} for r in repos]
    resp = http_request("POST", path, {"records": records}, token=token)
    if resp.get("code") != 0:
        raise RuntimeError(f"批量写入失败: {resp}")
    return resp["data"]["records"]


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

    print("列出旧记录...")
    old_ids = list_all_record_ids(token)
    print(f"  共 {len(old_ids)} 条旧记录")

    print("删除旧记录...")
    batch_delete_records(token, old_ids)
    time.sleep(0.5)

    print(f"写入 {len(repos)} 条新记录(快照日期 {snapshot_date})...")
    batch_create_records(token, repos, snapshot_date)

    print("完成。")


if __name__ == "__main__":
    main()
