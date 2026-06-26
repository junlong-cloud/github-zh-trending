# GitHub 中文热门项目榜

每日 09:00 (Asia/Shanghai) 自动刷新的中文 GitHub 新仓库榜单。

🌐 **在线访问**:https://github-zh-trending.netlify.app

## 工作机制

- `fetch_data.py` 调用 GitHub Search API,拉取最近 7 天创建、按 star 排序的新仓库,逐个检查 description / README 是否含中文,凑够 Top 10 写入 `data.json`
- `index.html` 是纯静态单页,从同目录 `data.json` 读数据渲染(瑞士国际主义风格)
- `.github/workflows/refresh.yml` 每天 01:00 UTC(= 北京 09:00)自动跑一次脚本并部署到 Netlify

## 本地运行

```bash
# 准备 .env(放 GitHub 只读 token,提升 API 限流)
echo "GITHUB_TOKEN=ghp_xxxxx" > .env

# 拉数据
python fetch_data.py

# 启个本地服务器看页面(不能直接双击 index.html,fetch 会被 CORS 拦)
python -m http.server 8800
# 打开 http://localhost:8800/
```

## 所需 GitHub Secrets

| Secret 名称 | 用途 | 怎么拿 |
|---|---|---|
| `GH_READ_TOKEN` | 给 fetch_data.py 用,提升 GitHub API 限流到 5000/小时 | GitHub Settings → Developer settings → Personal access tokens |
| `NETLIFY_AUTH_TOKEN` | GitHub Actions 部署到 Netlify 的授权 | Netlify → User settings → Applications → Personal access tokens |
| `NETLIFY_SITE_ID` | 目标 Netlify 站点 ID | 当前站点的 site_id:`539e3bd0-8b29-413c-9573-e1847276bf61` |
