# 服务器部署与更新

服务器入口：`http://139.196.11.38:8889`。Nginx 托管前端，并将 `/api/` 转发至仅监听本机的 Go 网关 `19000`。Docker Compose 管理 FastAPI、Go 网关、MySQL、Redis；小内存服务器使用 Milvus Lite 文件保存向量，已有 EqV2 服务继续从 8888 调用。

## 首次部署 / 日常更新（在项目根目录运行）

本机需要 Python、Node/npm、Go、Git；Python 依赖：`python -m pip install paramiko python-dotenv tzdata`。先在本地 `.env` 或 `backend/.env` 配好 LLM、Embedding、EqV2。服务器需要 Docker Compose、Nginx，安全组放行 TCP 8889。

```powershell
python ops/deploy.py
```

输入 SSH 密码（不会保存）。自动进行前端类型检查和构建、Linux 网关交叉编译、上传发布包、构建带版本号的镜像和健康检查。首次部署自动生成数据库密码和 JWT 密钥。后续更新保留服务器环境配置，如需同步本地配置，显式运行 `python ops/deploy.py --sync-env`。

切换前还会在临时容器中检查 RAG 向量检索和长期记忆的读写，不调用外部 Embedding 或 LLM。主要 Python 依赖版本固定在 `ops/requirements-server.txt`。

后端打包包含 Git 已跟踪文件的当前工作区内容；新建源码文件应先 `git add`，推荐提交后再发布。源码、前端构建产物放在独立版本目录；不上传本地聊天记录、数据库、附件、日志和 `.env` 文件。

```powershell
python ops/deploy.py --status
python ops/deploy.py --rollback
python ops/check.py
```

更新前自动备份 MySQL 和 SQLite。激活失败自动恢复上一版代码；手动回滚同样保留当前数据。数据库结构不兼容的变更需要另行安排数据迁移/恢复，不能仅靠代码回滚。

`check.py` 检查公网前端、SPA 路由、游客鉴权、工具列表及会话写入/读取，并删除测试会话；不会调用 LLM 或提交量化计算。需要 `requests`（`python -m pip install requests`）。

## 服务器目录

```text
/opt/quantum-agent-platform/
  releases/<时间-提交号>/  源码、前端构建产物、Compose 配置
  current -> releases/... 当前版本
  previous -> releases/... 上一版
  shared/
    app.env               LLM / Embedding / EqV2 配置（600 权限）
    compose.env           自动生成的数据库密码和 JWT 密钥（600 权限）
    mysql/ redis/ data/   持久化数据（SQLite、向量、附件、计算产物）
    logs/ backups/       日志和更新前数据库备份
```

在服务器查看日志：

```bash
cd /opt/quantum-agent-platform/current
docker compose --env-file /opt/quantum-agent-platform/shared/compose.env --env-file release.env -f ops/compose.yml logs --tail=100 app auth
```

旧版本和镜像不会自动删除，方便回滚；磁盘不足时确认不再需要后再清理。发布期间后端有短暂重启，目前不是零停机部署。
