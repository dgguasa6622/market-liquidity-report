# 市场流动性统计报告

> 每日自动抓取中国人民银行公开市场业务数据，生成市场流动性统计报告。

## 📊 报告内容

| 项目 | 数据来源 | 统计区间 |
|------|---------|---------|
| 7天/14天逆回购 | 央行交易公告 | 近2个月 |
| 买断式逆回购 | 央行业务公告 | 近24个月 |
| 中期借贷便利（MLF） | 央行工作信息 | 近24个月 |

## 🚀 部署步骤

### 1. 创建 GitHub 仓库

在 GitHub 上创建一个新仓库（例如 `market-liquidity-report`），将以下文件上传到仓库根目录：

```
fetch_pbc_data.py          # 数据抓取脚本
update-report.yml          # GitHub Actions 工作流（需放入 .github/workflows/）
docs/index.html            # 初始占位页面
README.md                  # 本说明文件
.gitignore                 # Git 忽略配置
```

**注意**：`update-report.yml` 必须放在 `.github/workflows/` 目录下。

### 2. 启用 GitHub Pages

1. 进入仓库 **Settings → Pages**
2. Source 选择 **GitHub Actions**
3. 保存

### 3. 启用通知

**方式一：Watch 仓库（推荐）**
- 进入仓库主页，点击 **Watch → Custom → Activities → Commits**
- 每次报告更新时会收到 GitHub 通知（邮件/推送通知）

**方式二：GitHub Email 通知**
- 进入 GitHub **Settings → Notifications → Email**
- 勾选 **Email notifications**，选择接收仓库活动通知

**方式三：Actions 页面查看**
- 每次运行后可在 **Actions** 页面查看运行结果和报告摘要

### 4. 首次手动运行

1. 进入仓库的 **Actions** 标签页
2. 选择 **Update Market Liquidity Report** 工作流
3. 点击 **Run workflow** 手动触发首次运行
4. 运行完成后，报告将自动部署到 GitHub Pages

## 📁 项目结构

```
├── .github/
│   └── workflows/
│       └── update-report.yml    # GitHub Actions 工作流
├── docs/
│   ├── index.html               # 生成的HTML报告（自动更新）
│   └── data.json                # 原始数据（自动更新）
├── fetch_pbc_data.py            # 数据抓取脚本
├── README.md                    # 说明文档
└── .gitignore                   # Git 忽略配置
```

## ⚙️ 自定义配置

### 修改执行时间

编辑 `.github/workflows/update-report.yml` 中的 `cron` 表达式：

```yaml
schedule:
  - cron: '0 2 * * 1-5'  # UTC 02:00 = 北京时间 10:00，周一至周五
```

如需包含周末运行，改为：
```yaml
  - cron: '0 2 * * *'  # 每天都运行
```

### 修改统计区间

编辑 `fetch_pbc_data.py` 中的参数：

```python
# 逆回购统计区间（天）
cutoff = (TODAY_DT - timedelta(days=62))  # 近2个月

# 买断式逆回购/MLF统计区间（天）
cutoff = (TODAY_DT - timedelta(days=730))  # 近24个月
```

## 📝 数据来源

- [中国人民银行 - 公开市场业务交易公告](https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/index.html)
- [中国人民银行 - 买断式逆回购公告](https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/5492845/index.html)
- [中国人民银行 - MLF工作信息](https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125437/125446/125873/index.html)

## ⚠️ 注意事项

1. **数据仅供参考**，请以央行官方数据为准
2. 央行网站可能偶尔无法访问，导致当日抓取失败（Actions 会自动重试）
3. 节假日央行不发布公告，报告将沿用上一工作日数据
4. 如需周末也运行，将 cron 改为 `0 2 * * *`

## License

MIT
