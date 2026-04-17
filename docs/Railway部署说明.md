# Railway 部署说明

## 目标

把当前项目部署为一个可通过 GitHub 自动发布的 Railway 演示环境。

## 推荐架构

Railway 项目中建议创建两个服务：

1. `zfmd-postgres`
2. `zfmd-odoo`

其中：

- `zfmd-postgres` 使用 Railway 自带 PostgreSQL 模板
- `zfmd-odoo` 使用本仓库的 `Dockerfile`
- 给 `zfmd-odoo` 挂一个 Volume 到 `/var/lib/odoo`

## 一、推送到 GitHub

1. 在 GitHub 新建一个仓库
2. 把当前项目推送上去
3. 确认以下目录不要入库：
   - `postgres_data`
   - `odoo/data`
   - `backup-*.zip`

## 二、在 Railway 创建数据库

1. 新建 Railway Project
2. 添加 `PostgreSQL`
3. 记下或引用以下变量：
   - `PGHOST`
   - `PGPORT`
   - `PGUSER`
   - `PGPASSWORD`
   - `PGDATABASE`

## 三、在 Railway 创建 Odoo 服务

1. 选择 `Deploy from GitHub Repo`
2. 选择当前仓库
3. Railway 会使用仓库根目录的 `Dockerfile`

## 四、给 Odoo 服务配置变量

至少配置：

- `ADMIN_PASSWORD`
- `LIST_DB=False`
- `PROXY_MODE=True`

数据库变量通常可直接引用 PostgreSQL 服务提供的：

- `PGHOST`
- `PGPORT`
- `PGUSER`
- `PGPASSWORD`
- `PGDATABASE`

如果 Railway 自动变量和你的手动配置冲突，建议改用我们仓库支持的自定义变量：

- `ODOO_DB_HOST`
- `ODOO_DB_PORT`
- `ODOO_DB_USER`
- `ODOO_DB_PASSWORD`
- `ODOO_DB_NAME`

推荐直接这样配：

- `ODOO_DB_HOST=${{Postgres.PGHOST}}`
- `ODOO_DB_PORT=${{Postgres.PGPORT}}`
- `ODOO_DB_NAME=${{Postgres.PGDATABASE}}`
- `ODOO_DB_USER=odoo`
- `ODOO_DB_PASSWORD=你给 odoo 用户设置的密码`

## 五、挂载 Volume

在 `zfmd-odoo` 服务上新增持久化存储：

- Mount Path：`/var/lib/odoo`

这是必须的，否则附件、会话和文件存储无法持久化。

## 六、首次初始化

部署完成后，打开 Railway 提供的域名。

第一次进入时：

1. 创建数据库
2. 安装 `zfmd_pm` 模块
3. 创建管理员账号
4. 再按需要创建演示账号和客户账号

如果你希望把当前本机数据库也迁过去，建议后续单独做数据库导出/导入，不要直接拷贝本地 `postgres_data`。

## 七、绑定域名

Railway 默认会给一个 `*.up.railway.app` 地址。

如果需要正式一点的演示地址，可以绑定自有域名，例如：

- `demo.yourdomain.com`

## 八、上线建议

演示环境建议优先做到：

- 只读演示账号
- 关闭数据库列表
- 强管理员密码
- 定期手动备份数据库

## 九、当前仓库内已准备好的文件

- [Dockerfile](C:\Users\Administrator\Documents\New%20project%202\Dockerfile)
- [deploy/start-odoo.sh](C:\Users\Administrator\Documents\New%20project%202\deploy\start-odoo.sh)
- [odoo/odoo.railway.conf](C:\Users\Administrator\Documents\New%20project%202\odoo\odoo.railway.conf)
- [.env.railway.example](C:\Users\Administrator\Documents\New%20project%202\.env.railway.example)

## 十、下一步可继续做的事

- 增加一份 `GitHub 提交说明`
- 增加 `数据库初始化脚本`
- 增加 `Railway 演示环境专用账号初始化脚本`
