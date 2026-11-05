# 图书管理后台 API 清单

Base URL（本地）：`http://127.0.0.1:5001`  
统一前缀：`/api/v1`  
认证：`Authorization: Bearer <access_token>`  
请求追踪：可选 `X-Request-ID`，服务端在响应头与响应体回传。

## 种子账号

| 用户名 | 密码 | 角色 | 状态 |
|---|---|---|---|
| admin | admin123 | admin | active |
| reader | reader123 | reader | active |
| reader2 | reader123 | reader | active |
| disabled | disabled123 | reader | disabled |

> 仅供本地 Demo。生产环境禁止使用默认口令。

## 12 个业务接口

| # | 方法 | 路径 | 权限 | 说明 |
|---:|---|---|---|---|
| 1 | POST | `/auth/login` | 公开 | 登录换 Token |
| 2 | POST | `/auth/logout` | 登录 | 注销当前 Token |
| 3 | GET | `/auth/me` | 登录 | 当前用户信息 |
| 4 | GET | `/books` | 登录 | 分页/分类/状态/关键字/排序 |
| 5 | GET | `/books/{id}` | 登录 | 图书详情 |
| 6 | POST | `/books` | admin | 新增图书 |
| 7 | PUT | `/books/{id}` | admin | 部分更新 |
| 8 | DELETE | `/books/{id}` | admin | 删除（有借阅历史则 409） |
| 9 | POST | `/books/{id}/borrow` | reader | 借书，扣库存并生成记录 |
| 10 | POST | `/borrows/{id}/return` | 本人/admin | 还书，恢复库存 |
| 11 | GET | `/borrows` | 登录 | 读者仅本人，管理员全量 |
| 12 | GET | `/stats/overview` | admin | 图书/库存/借阅/分类聚合 |

运维探活：`GET /healthz`（不计入 12 个业务接口）。

## 统一成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "request_id": "f1f974bab2444470bf199e227b2f3247"
}
```

## 统一错误响应

```json
{
  "code": 40001,
  "message": "price 必须在 0 到 9999 之间",
  "data": null,
  "details": {"field": "price", "reason": "range"},
  "request_id": "..."
}
```

## 业务码

| code | HTTP | 含义 |
|---:|---:|---|
| 0 | 200/201 | 成功 |
| 40001 | 400 | 参数校验/类型/范围/枚举错误 |
| 40002 | 400 | 缺少必填字段 |
| 40101 | 401 | 未提供 Token |
| 40102 | 401 | Authorization 方案错误 |
| 40103 | 401 | Token 无效/过期/签名错误 |
| 40104 | 401 | Token 已注销 |
| 40105 | 401 | Token 对应用户不存在 |
| 40110 | 401 | 用户名或密码错误 |
| 40301 | 403 | 角色越权 |
| 40302 | 403 | 账号禁用 |
| 40303 | 403 | 只能归还本人借阅 |
| 40400 | 404 | 路由不存在 |
| 40401 | 404 | 图书不存在 |
| 40402 | 404 | 借阅记录不存在 |
| 40500 | 405 | HTTP 方法不允许 |
| 40901 | 409 | ISBN 重复 |
| 40902 | 409 | 图书存在借阅历史，不可删除 |
| 40903 | 409 | 图书已下架 |
| 40904 | 409 | 库存不足 |
| 40905 | 409 | 借阅已归还 |
| 41300 | 413 | 请求体过大（预留） |
| 50000 | 500 | 未处理异常 |

## 约束

- ISBN：13 位（`978/979` 开头）或 10 位，允许末位 `X`。
- 分类：`科技 / 文学 / 历史 / 经管 / 少儿`。
- 价格：`0 ~ 9999`，最多两位小数。
- 库存：`0 ~ 999`。
- 单次借阅：`1 ~ 5` 本，且不能超过库存。
- 借期：30 天。
- 分页：`page >= 1`，`1 <= page_size <= 50`。
- 排序白名单：`created_at / price / title / stock`，方向 `asc / desc`。
