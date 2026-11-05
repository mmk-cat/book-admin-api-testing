# 接口测试设计说明

## 1. 范围与统计口径

- 业务接口：**12** 个（不含 `/healthz` 探活）。
- 接口用例：**144** 条；其中按接口归属 **135** 条，横切契约/安全 **9** 条。
- 框架自检：4 条（重试策略、脱敏、双环境配置），不计入接口用例。
- pytest 总计：**148** 条，全部通过。
- 逆向/异常：**104** 条，占接口用例 72.2%。
- 含数据库直查断言：17 条。

统计由 `scripts/collect_metrics.py` 从 pytest 收集结果自动生成，禁止手工改数。

## 2. 测试点拆解

| 接口 | 核心测试点 |
|---|---|
| POST /auth/login | 正确账号、错误密码、不存在用户、禁用账号、缺参、null、空串、类型错误、超长、SQL 注入、非 JSON 请求体 |
| POST /auth/logout | 正常注销、未登录、Token 注销后不可复用 |
| GET /auth/me | 正常返回、缺 Header、错误认证方案、格式错误、签名篡改、过期、用户不存在 |
| GET /books | 默认分页、翻页、分类/状态/关键字、排序、组合条件、total 与 DB 一致、非法分页/排序/枚举、SQL 注入、未授权 |
| GET /books/{id} | 正常详情、不存在、id=0、非整数 id、字段类型 |
| POST /books | 3 组合法数据、6 类缺参、null/空串、bool 冒充 int、小数库存、负价格、价格精度、库存/价格边界、超长、ISBN 格式、重复 ISBN、角色越权、落库字段 |
| PUT /books/{id} | 部分更新、空更新、未知字段、非法字段、重复 ISBN、404、越权 |
| DELETE /books/{id} | 正常删除、有借阅历史冲突、404、越权 |
| POST /books/{id}/borrow | 正常借阅、库存扣减/记录落库、数量 0/负/超 5/字符串/bool、超库存、下架、零库存、404、未登录、管理员越权、失败不扣库存 |
| POST /borrows/{id}/return | 正常归还、库存恢复、重复归还、他人借阅、404、未登录、管理员代还 |
| GET /borrows | 读者仅本人、管理员全量、状态过滤、分页、非法状态、未登录 |
| GET /stats/overview | 管理员聚合值与 DB 一致、读者 403、未登录 401 |

## 3. 用例设计方法

### 等价类

- 角色：管理员 / 读者 / 未登录 / 禁用用户。
- 图书状态：`available` / `borrowed` / `off_shelf`。
- 借阅状态：`borrowed` / `returned`。
- 字段类型：string / number / bool / null / 缺失 / 空串 / 非法枚举。

### 边界值

| 字段 | 下边界 | 合法内点 | 上边界 | 越界 |
|---|---:|---:|---:|---:|
| page | 1 | 2 | 100000 | 0 / -1 |
| page_size | 1 | 5 | 50 | 0 / 51 |
| title 长度 | 1 | 10 | 100 | 101 |
| author 长度 | 1 | 5 | 50 | 51 |
| price | 0 | 39.9 | 9999 | -1 / 10000 / 39.999 |
| stock | 0 | 3 | 999 | -1 / 1000 |
| borrow quantity | 1 | 2 | 5 | 0 / 6 / 超库存 |

### 错误推测

- 布尔值在 Python 中可被 `isinstance(x, int)` 误判，因此 stock/quantity 明确拒绝 `true/false`。
- `null` 与字段缺失返回不同业务码：缺失 `40002`，类型/空值 `40001`。
- 重复提交创建同一 ISBN 返回 `40901`，而不是 500。
- SQL 注入串作为普通关键字参与参数化 `LIKE`，不拼 SQL。
- 过期 Token 用同一签名算法离线构造，避免 sleep 等待。
- 登出后 Token 进入黑名单，重放返回 `40104`。
- 库存不足失败必须保证库存不变且不产生借阅记录。

## 4. 断言分层

1. HTTP 状态码；
2. 业务码 `code`；
3. 响应字段存在性与类型（`book.price` 数字、`book.stock` int、ISO 时间）；
4. 分页元数据与数据库 `COUNT(*)` 一致；
5. 关键写操作直查数据库：库存、借阅状态、`returned_at`、审计时间；
6. 表结构：SQLite `NUMERIC(10,2)/INTEGER`，MySQL `decimal(10,2)/int`。

## 5. 执行与追溯

- Allure：`feature/story/title` + 请求失败附件。
- 每个请求带 `X-Request-ID`，服务端回传，并在 `logs/api_tests.log` 记录耗时。
- 结果：
  - `reports/junit.xml`
  - `reports/pytest-report.html`
  - `reports/allure-results/`
  - `reports/metrics.json` / `reports/metrics.md`
  - `reports/dev_sqlite/server.log`（SQLite 运行快照）

