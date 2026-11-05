# 图书管理后台接口自动化测试框架

基于 **Python + pytest + requests + YAML + Allure + Jenkins + MySQL** 的接口自动化项目。仓库同时包含一个可独立启动的图书管理后台 Demo（Flask + SQLite/MySQL），因此克隆后不需要依赖外部系统即可跑通全部用例。

## 已验收结果

| 指标 | 实测值 |
|---|---:|
| 业务接口 | **12** 个 |
| 接口用例 | **144** 条（另含 4 条框架自检） |
| pytest 收集/通过 | **148 / 148 passed** |
| 逆向异常用例 | **104** 条 |
| 冒烟用例 | 19 条 |
| 含直接落库断言的用例 | 17 条 |
| pytest 耗时 | **22.67 s** |
| 回归命令总耗时 | **25.62 s** |
| 测试环境 | Windows 11 / Python 3.12 / MariaDB 11.4.13（MySQL 协议，pymysql） |

> 同时保留 SQLite 零依赖环境的报告快照：`reports/dev_sqlite/`（148 passed，14.43 s）。  
> 原始结果：`reports/pytest-report.html`、`reports/junit.xml`、`reports/allure-results/`、`reports/metrics.json`、`reports/mysql_run.md`。  
> Allure HTML 已生成：`reports/allure-report/index.html`（148 passed / 0 failed）；也可用 `allure serve reports/allure-results` 动态查看。

## 快速开始（零外部依赖）

```powershell
cd "C:\Users\LENOVO\Desktop\项目\01_book_admin_api_testing"
python -m pip install -r requirements.txt
python scripts/run_regression.py
```

`dev` 环境会自动：

1. 删除 `runtime/book_admin.db`，启动带种子数据的 Demo API（`127.0.0.1:5001`）；
2. 执行 148 条用例并生成 JUnit、pytest-html、Allure 原始结果；
3. 生成 `reports/metrics.json` 与 `reports/metrics.md`；
4. 关闭 Demo API。

也可以手动启动：

```powershell
$env:PYTHONPATH="backend"
$env:DB_BACKEND="sqlite"
python -m book_admin.run
# 另开终端
python -m pytest -q
```

## MySQL / Docker 模式

```powershell
docker compose up -d --build
python scripts/wait_for_service.py http://127.0.0.1:5001/healthz 120
python scripts/run_regression.py --env test
docker compose down -v
```

`--env test` 使用 `config/config.yaml` 中的 MySQL 配置；测试通过 **pymysql** 直连数据库，校验 `DECIMAL(10,2)`、`INT` 等字段类型和落库值。  
本机没有 Docker，因此验收时用便携版 **MariaDB 11.4.13** 在 `127.0.0.1:3307` 跑通了完全相同的一套用例（见 `reports/mysql_run.md`）；`docker-compose.yml` 面向标准 MySQL 8.4。  
Jenkins 每日回归定义在 `ci/Jenkinsfile`，包含 MySQL 启动、全量回归、JUnit/Allure 发布和归档。

## 目录结构

```
01_book_admin_api_testing/
├─ backend/book_admin/        # Flask Demo：12 个业务接口 + /healthz
│  └─ sql/                    # SQLite / MySQL 双 schema
├─ common/
│  ├─ base_request.py         # Token 鉴权、连接池、超时、GET 安全重试、脱敏日志
│  ├─ db_client.py            # pymysql / sqlite3 落库断言
│  ├─ assertions.py           # 统一断言 + Allure 失败附件
│  ├─ token_tools.py          # 过期/篡改/伪造 Token 构造
│  └─ data_loader.py          # YAML 数据与占位符展开
├─ config/config.yaml         # dev(SQLite) / test(MySQL) 双环境
├─ data/*.yaml                # 用例数据：登录、查询、写接口、借阅
├─ tests/                     # 148 条 pytest 用例
├─ scripts/                   # 一键回归、指标采集、服务探活
├─ ci/Jenkinsfile             # 每日 02:xx 回归
├─ Dockerfile / docker-compose.yml
└─ reports/                   # 实测报告
```

## 框架设计要点

- **统一请求层**：`BaseRequest` 负责登录换 Token、Bearer 注入、Session 连接池、5s 超时、`X-Request-ID` 透传、日志脱敏。
- **安全重试**：使用 urllib3 `Retry`，只对 `GET/HEAD/OPTIONS` 的 502/503/504 重试；`POST/PUT/DELETE` 不自动重试，避免重复写库。
- **环境与数据分离**：环境在 `config/config.yaml`，测试数据在 `data/*.yaml`，代码只保留测试逻辑。
- **双层校验**：HTTP 状态码 + 业务码 + 响应字段类型 + 数据库落库值/字段类型。示例：创建图书后直查 `books`，校验价格、库存、审计时间。
- **逆向设计**：缺参、`null`、类型错误（含 bool 冒充 int）、边界/超长、非法枚举、重复 ISBN、SQL 注入、越权、Token 过期/伪造/注销、分页越界。
- **可观测性**：每个请求记录 request_id、状态码、耗时；失败时自动把响应体与响应头附到 Allure。
- **双数据库后端**：Demo 用 SQLite 可零依赖运行；CI 用 MySQL 验证真实 `pymysql` 链路和 `DECIMAL` 类型。

## 双环境

| 环境 | 数据库 | 启动方式 | 用途 |
|---|---|---|---|
| `dev` | SQLite | pytest fixture 自动启动 | 本机快速回归、演示 |
| `test` | MySQL 8.4 | `docker compose` | Jenkins / 真实数据库校验 |

覆盖命令：

```powershell
python -m pytest --env dev   # 默认
python -m pytest --env test  # 需要 MySQL + API 已启动
```

## 测试设计

详细测试点、边界值、等价类与计数见 [`docs/TEST_DESIGN.md`](docs/TEST_DESIGN.md)，接口清单见 [`docs/API.md`](docs/API.md)。

接口用例分布（共 144 条；另有 9 条横切契约/安全检查）：

| 接口组 | 用例数 |
|---|---:|
| POST /auth/login | 17 |
| POST /auth/logout | 2 |
| GET /auth/me | 7 |
| GET /books | 27 |
| GET /books/{id} | 4 |
| POST /books | 33 |
| PUT /books/{id} | 12 |
| DELETE /books/{id} | 5 |
| POST /books/{id}/borrow | 13 |
| POST /borrows/{id}/return | 6 |
| GET /borrows | 6 |
| GET /stats/overview | 3 |
| 横切契约/安全 | 9 |

## 简历占位符回填

| 原始项 | 本项目实测 |
|---|---|
| 接口数 | **12** 个业务接口（另有 `/healthz` 运维探活，不计入） |
| 用例数 | **144** 条接口用例 + 4 条框架自检；pytest 共 **148** 条 |
| 手工回归估算 | 约 2 小时（按 144 条约 50 秒/条估算） |
| 自动化回归 | 本机 MariaDB 全量命令 **25.62 秒**；建议写“降至 1 分钟内”，不要虚构 8 分钟 |

## 已知边界

- Demo 服务用于测试演示，不替代生产图书系统；密码哈希、Token 签名和参数校验均为教学级实现。
- 本机未安装 Docker；使用 MariaDB 11.4.13 完成了真实 `pymysql` 链路验证，标准 MySQL 8.4 的 compose 配置已提供但未在本机启动。
- Allure CLI 未预装；静态 HTML 已生成到 `reports/allure-report/index.html`。安装 CLI 后可用 `allure serve reports/allure-results` 动态查看。

