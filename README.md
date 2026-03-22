# 豆瓣读书 Top250 爬虫（导出 Excel）

自动抓取 [豆瓣读书 Top250](https://book.douban.com/top250) 的全部书籍信息，并导出为 Excel 文件。

## 功能特性

- 自动抓取 Top250（列表页 + 详情页）
- 自动重试（指数退避 + 抖动）
- 单本失败不中断，错误写入 `crawl_error`
- 自动去重（按 `subject_id`）
- 导出 Excel（sheet: `top250`）
- 支持命令行参数（输出路径、超时、重试、延迟、测试限量）

## 环境要求

- Python 3.9+

## 安装依赖

```bash
python -m pip install -r requirements.txt
```

## 使用方式

默认全量抓取 250 本并输出 `douban_top250_books.xlsx`：

```bash
python douban_top250_to_excel.py
```

指定参数示例：

```bash
python douban_top250_to_excel.py --output data/top250.xlsx --min-delay 1 --max-delay 2 --timeout 20 --retries 3
```

仅抓取前 5 本（测试）：

```bash
python douban_top250_to_excel.py --limit 5 --min-delay 0 --max-delay 0
```

## 输出字段

固定字段：

- `rank`
- `subject_id`
- `title`
- `book_url`
- `cover_url`
- `rating`
- `rating_count`
- `list_meta_raw`
- `quote`
- `content_intro`
- `author_intro`
- `info_raw`
- `crawl_error`
- `crawled_at`

动态字段：

- `info_*`（来自详情页 `#info` 的所有键值，如 `info_作者`、`info_出版社`、`info_ISBN` 等）

## 测试

运行单元测试：

```bash
python -m pytest -q
```

运行网络集成测试（默认关闭）：

```bash
# Windows PowerShell
$env:RUN_NETWORK_TESTS="1"
python -m pytest -q tests/test_integration_network.py
```

## 说明

- 抓取目标网站可能存在反爬机制，建议保留请求延迟参数，不要高频请求。
- 本项目仅用于学习与技术交流，请遵守目标网站的服务条款与法律法规。
