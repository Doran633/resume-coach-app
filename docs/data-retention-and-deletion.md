# 数据保留与删除

## 默认保留期

| 数据 | 默认期限 | 配置项 |
| --- | ---: | --- |
| 经历输入和生成结果 | 30 天 | `USER_CONTENT_RETENTION_DAYS` |
| 生成的 DOCX | 7 天 | `GENERATED_FILE_RETENTION_DAYS` |
| 脱敏埋点、反馈和会话 | 90 天 | `ANALYTICS_RETENTION_DAYS` |
| SQLite 备份 | 14 天 | `BACKUP_RETENTION_DAYS` |

期限应与页面隐私说明保持一致。修改后端保留期时，同时更新前端构建变量 `VITE_USER_CONTENT_RETENTION_DAYS` 并重新构建。

## 用户主动删除

隐私政策页提供“删除我的数据”。浏览器通过服务端签名、HttpOnly、Secure Cookie 证明当前匿名身份；服务端只删除该身份关联的经历、结果、Claim、调用记录、版本、反馈、事件、会话和 DOCX。

删除请求会校验同源 `Origin`/`Referer`，生成进行中时返回冲突；文件先移动到隔离目录，数据库提交失败时恢复文件。不能安全处理关联文件时，请求整体失败，不返回静默部分成功。

删除成功后前端清除草稿、结果和本地匿名标识。用户清除 Cookie 后可能失去对旧数据的身份凭证，因此隐私联系邮箱仍应作为人工删除渠道。

## 自动清理

先预览：

```bash
.venv/bin/python scripts/cleanup_retained_data.py --dry-run
```

执行清理：

```bash
.venv/bin/python scripts/cleanup_retained_data.py
```

脚本先按关系删除数据库记录，再清理对应文件；运行日志只记录数量，不记录经历正文。失败时退出码非零，运维任务应据此告警。

## 备份边界

备份包含生产数据库中的用户内容，因此备份目录必须使用最小权限。备份不包含 `.env`、API Key 或 Cookie 密钥。删除生产数据不会追溯修改历史备份；到期备份由 `BACKUP_RETENTION_DAYS` 自动清理，并应在隐私说明中如实披露备份保留窗口。
