# zfmd-pm-4.17 开发工作流指南

## 开发环境

- **项目路径**: `~/temp/zfmd-pm-4.17`
- **Odoo 版本**: 17
- **Python 版本**: 3.9+

## 代码质量工具

已配置以下工具：

| 工具 | 用途 | 命令 |
|------|------|------|
| **flake8** | 代码风格检查 | `python3 -m flake8 addons/zfmd_pm/` |
| **black** | 代码格式化 | `python3 -m black addons/zfmd_pm/` |
| **isort** | import 排序 | `python3 -m isort addons/zfmd_pm/` |
| **pre-commit** | Git 提交前自动检查 | `git commit` 时自动触发 |

## 常用命令

### 1. 格式化代码
```bash
cd ~/temp/zfmd-pm-4.17
python3 -m black addons/zfmd_pm/
python3 -m isort addons/zfmd_pm/
```

### 2. 检查代码问题
```bash
python3 -m flake8 addons/zfmd_pm/
```

### 3. 提交代码
```bash
git add .
git commit -m "描述你的修改"
# pre-commit 会自动运行 black, isort, flake8
```

## 使用 Codex 开发

### 方式 1：通过 OpenClaw Codex Agent

1. 在 webchat 中切换到 Codex agent
2. 告诉 Codex 你要修改的内容
3. Codex 会直接编辑代码文件

### 方式 2：通过 CLI 调用 Codex

```bash
# 在项目中启动 Codex
cd ~/temp/zfmd-pm-4.17
codex

# 或者使用 acpx
acpx codex -d ~/temp/zfmd-pm-4.17
```

## 开发流程建议

1. **先拉取最新代码**
   ```bash
   git pull origin main
   ```

2. **创建功能分支**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **使用 Codex 编写代码**
   - 描述清楚需求
   - 让 Codex 遵循现有代码风格
   - 注意 Odoo 17 的 API 规范

4. **运行代码检查**
   ```bash
   python3 -m black addons/zfmd_pm/
   python3 -m isort addons/zfmd_pm/
   python3 -m flake8 addons/zfmd_pm/
   ```

5. **测试代码**
   ```bash
   # 重启 Docker 容器加载新代码
   docker compose restart odoo
   
   # 在 Odoo 中更新模块
   # 设置 → 技术 → 更新模块列表
   # 然后升级 zfmd_pm 模块
   ```

6. **提交代码**
   ```bash
   git add .
   git commit -m "feat: 添加 xxx 功能"
   git push origin feature/your-feature-name
   ```

## 注意事项

- 所有 Python 文件行宽限制 120 字符
- import 语句会自动排序
- 提交前会自动运行代码检查
- 如果检查失败，提交会被拒绝
