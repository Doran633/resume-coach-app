# 数据库迁移准备

## 当前结论

公开测试阶段继续使用 SQLite。当前服务是单实例、写入规模有限，SQLite WAL、在线备份和恢复验证能够满足现阶段需要。v0.7.4 只审计迁移阻塞项，不修改生产数据库，也不连接 PostgreSQL。

## 何时开始迁移

出现以下任一持续信号时进入 PostgreSQL 迁移设计：

- 后端需要运行多个实例或独立后台 Worker。
- 日志持续出现数据库写锁或事务等待。
- 数据库接近 2 GB，或在线备份、恢复验证超过 5 分钟。
- 需要高可用、只读副本、时间点恢复或跨主机容灾。
- 生成、反馈、埋点和文件记录产生持续高并发写入。

## 当前阻塞项

- `ensure_v01_schema` 使用 SQLite `PRAGMA` 和直接 `ALTER TABLE`，应由正式迁移工具接管。
- 在线备份、完整性检查和恢复验证是 SQLite 专用实现。
- 需要逐项检查 `sqlite3`、`sqlite_master`、`PRAGMA` 和 `exec_driver_sql` 使用位置。
- 时间字段、外键删除顺序、连接池和事务隔离需要在 PostgreSQL 临时环境验证。

## 审计命令

```bash
.venv/bin/python scripts/audit_database_portability.py \
  --backups /var/backups/resume-coach
```

结果位于 `backend/reports/database-portability-latest.md`。报告只包含表名、数量、大小、耗时和代码阻塞项，不包含用户经历或简历正文。

## 未来迁移原则

1. 先在临时 PostgreSQL 中创建结构并迁移匿名化副本。
2. 对表数量、行数、外键和关键查询做双边校验。
3. 演练回滚后再安排短维护窗口。
4. 切换前创建并验证最后一份 SQLite 在线备份。
5. 不在缺少恢复方案时直接修改生产 `DATABASE_URL`。
