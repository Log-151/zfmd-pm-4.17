# 兆方美迪项目管理系统

这是基于 Odoo 17 二次开发的项目管理系统原型，目标是把 `合同台账 -> 开工申请 -> 服务记录 -> 开票登记 -> 回款登记 -> 应收计划 -> 数据看板` 串成一条业务主线。

当前仓库同时支持两种使用方式：

- 本地开发：继续使用 `docker-compose.yml`
- 云端部署：使用 `Dockerfile` 部署到 Railway

## 目录说明

- `addons/zfmd_pm`
  - 自定义业务模块
- `docs`
  - 方案、字段映射、试用说明、反馈清单
- `odoo`
  - Odoo 配置文件
- `deploy`
  - 云端启动脚本
- `scripts`
  - 历史导入、修复、检查脚本

## 本地开发

启动：

```bash
docker compose up -d
```

访问：

- `http://127.0.0.1:8069`

## Railway 部署

推荐结构：

1. Railway PostgreSQL 服务
2. Railway Odoo 服务
3. Odoo 服务挂载持久化 Volume 到 `/var/lib/odoo`

仓库已经包含 Railway 所需文件：

- `Dockerfile`
- `deploy/start-odoo.sh`
- `odoo/odoo.railway.conf`
- `.env.railway.example`

详细步骤见：

- [Railway部署说明](docs/Railway部署说明.md)

## 当前业务范围

- 数据看板
- 合同台账
- 开工申请
- 服务记录
- 开票登记
- 回款登记
- 应收计划

## 说明

- `odoo/data` 和 `postgres_data` 为本地运行数据目录，不建议提交到 GitHub。
- 当前仓库适合先部署演示环境和测试环境，待需求稳定后再继续加固正式环境能力。

