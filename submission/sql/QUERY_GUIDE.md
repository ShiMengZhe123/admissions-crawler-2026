# DataGrip 查询与截图说明

本地 MySQL 已验证连接并完成入库。DataGrip 五校汇总查询已在图形界面
实际执行，截图和 SQL 已保存：

- `results/database/datagrip_query_result.png`
- `results/database/datagrip_query.sql`

截图中的结果为：

| 项目 | 记录数 | 计划人数 |
|---|---:|---:|
| 中北大学 | 1486 | 7594 |
| 山西师范大学 | 758 | 5100 |
| 东北大学 | 746 | 4596 |
| 上海财经大学 | 34 | 84 |
| 河北工业大学 | 23 | 73 |
| 合计 | 3047 | 17447 |

如需再次截图或导出 CSV：

1. 在 DataGrip 连接 `127.0.0.1:3306`，数据库选择 `admissions`。
2. 打开 `submission/sql/queries.sql`。
3. 依次执行以下查询：
   - 五校招生计划汇总；
   - 每校各省记录数和计划人数；
   - 专业招生明细；
   - 空值/异常值检查；
   - 业务键重复检查；
   - OCR/人工核验状态。
4. 对结果集使用 DataGrip 的“Export Data”导出 CSV。
5. 截图时保留 DataGrip 左侧连接名、SQL 编辑器和结果网格，避免只截
   结果数字而缺少上下文。

命令行导出也可复现：

```powershell
.\.venv\Scripts\python.exe db_tools.py queries
```

导出位置：

`results/database/*.csv`

对于仅取得部分官方省份数据的学校，应按来源省份核对覆盖范围，不能为了
“五校全国完整”写入推测数据或其他年份数据。
