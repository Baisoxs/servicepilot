# Changelog

本项目的所有重要改动都记录在这里。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-11-27

### 新增

- 邮箱密码注册 / 登录，JWT access + refresh 双 token
- 会话与消息 CRUD：分页、软删除、按用户隔离
- SSE 流式对话：心跳保活、上游超时重试、并发信号量
- 会话列表 Redis 缓存（cache-aside + 版本号失效 + TTL 抖动）
- 按用户 60 秒滑动窗口限流（Redis ZSET + Lua 原子脚本）
- Streamlit 最小聊天页：登录 / 会话列表 / 流式显示
- Docker 多阶段构建、非 root 用户、HEALTHCHECK、优雅停机
- docker-compose 全栈编排，容器启动自动迁移

### 修复

- `/readyz` 依赖地址改为从配置读取，容器内不再误报 503
- 前端流式请求在 `raise_for_status` 前未读取响应体，导致 429 提示失败
