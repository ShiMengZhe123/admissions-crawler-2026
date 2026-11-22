# 官方来源与访问证据

## 中北大学

- 页面：<https://zbzs.nuc.edu.cn/info/1016/4547.htm>
- 页面返回：HTTP 200。
- 31 个省级链接已解析并保存在 `results/nuc/source_urls.json`。
- 原有 42 张图片已复用，没有全量重下载。
- `robots.txt` 返回 404。

## 山西师范大学

- 页面：<https://zsb.sxnu.edu.cn/info/1199/4459.htm>
- 页面返回：HTTP 200。
- HTML 主表可解析，示例和总计校验通过。
- `robots.txt` 返回 403，但公开招生计划页面本身可正常访问；请求仅低频
  获取必要页面。

## 东北大学

- 完整官方图片列表：
  <https://zs.neu.edu.cn/2026n/list.htm>
- 页面统计 31 条省级记录。
- `robots.txt` 返回 HTTP 200，内容为 `User-agent: * / Allow: /`。
- 旧的 `11195/list2.htm` 分页已失效；真实完整列表是 `2026n/list.htm`。

## 上海财经大学

- 官方查询页：
  <https://zs.sufe.edu.cn/zsjh/list.htm>
- 数据 iframe：
  <https://zs.sufe.edu.cn/_web/_apps/commonquery/commonquery/api/queryMatch/26.rst>
- iframe HTTP 200，包含年份、省市和四位数字验证码。
- 未自动识别、破解或绕过验证码。
- 官网“2026 年本科招生亮点”：
  <https://zs.sufe.edu.cn/0b/08/c3343a264968/page.htm>，仅含政策和
  规模说明，没有分省分专业明细。
- 官网“2026 年本科招生专业（类）目录”：
  <https://zs.sufe.edu.cn/08/c0/c3343a264384/page.htm>。当前请求被
  重定向到 `page.psp` 并返回 HTTP 410，未将该页作为计划数据源。
- 自动证据：`results/sufe/source_evidence.json`。

## 河北工业大学

- 学校主站：<https://www.hebut.edu.cn/>，HTTP 200。
- 主站明确链接本科生招生：<https://zs.hebut.edu.cn/>。
- 招生子站的 HTTP、HTTPS、IPv4 和 Playwright 真实浏览器访问均被
  重定向到 `/rump_frontend/access_forbidden/`，HTTP 403。
- 经官方搜索索引定位到校方公开路径
  <https://zs.hebut.edu.cn/Baokao/fenshu.html>（“录取分数及计划”），
  当前网络直连仍返回 WAF 403，未绕过。
- 未采用第三方汇总数据替代官方来源。
- 自动证据：`results/hebut/source_evidence.json`。

## 河南省阳光高考平台（省级官方补充）

- 上海财经大学：
  <https://10272.gaokao.haedu.cn/schoolPlan.html>
- 河北工业大学：
  <https://10080.gaokao.haedu.cn/schoolPlan.html>
- 页面返回 HTTP 200，标题包含对应学校，`history_list` 内嵌 2026 计划。
- 上海财大：页面声明 34 条，实际解析 34 条，84 人。
- 河北工大：页面声明 23 条，实际解析 23 条，73 人。
- 原始 HTML、拉取时间、响应字节和 SHA-256 保存在
  `evidence/official_sources/henan/`。

## 上海市教育考试院

- 官网公开检索确认存在《2026 年上海市普通高等学校招生专业目录》发行
  通知：
  <https://www.shmeea.edu.cn/page/02200/20260617/20353.html>
- 当前公开网页未提供可直接核验的整本计划电子数据，因此没有用征求
  志愿缺额计划替代初始招生计划。
