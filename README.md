# 兆方美迪项目管理系统

这是基于 Odoo 17 二次开发的项目管理系统原型，目标是把 `合同台账 -> 开工申请 -> 服务记录 -> 开票登记 -> 回款登记 -> 应收计划 -> 数据看板` 串成一条业务主线。

当前仓库以自管云服务器部署为主，推荐使用 `docker-compose.yml`，通过 volume 挂载 `./addons`，代码更新后容器直接读取当前源码。

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

## 云服务器部署

自管云服务器推荐直接使用仓库中的 `docker-compose.yml`。该方式会挂载当前源码目录，更新代码后执行模块升级和重启即可生效。

```bash
git pull
docker compose exec -T odoo odoo -d zfmd-PM -u zfmd_pm --stop-after-init --no-http
docker compose restart odoo
```

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
