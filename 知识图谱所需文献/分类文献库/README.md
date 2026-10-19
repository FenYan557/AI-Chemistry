# 分类文献库说明

整理日期：2026-09-29（"近3年"检索窗口：2023-09-29 ~ 2026-09-29）

## 主题范围（与原文献集一致）
钴/铜电沉积与电镀、通孔/盲孔/沟槽超共形填充、电镀添加剂（抑制剂、加速剂、整平剂、光亮剂）、
TSV/微导通孔/铜柱凸点、先进封装与互连金属化（含机器学习筛选添加剂、镀层织构/性能调控等相关方向）。

## 目标期刊（11 个分类目录）
Journal of Electroanalytical Chemistry · Electrochimica Acta · ACS Omega · Colloids and Surfaces A ·
Chemical Engineering Journal · Small · ACS Applied Materials & Interfaces · Journal of Materials Chemistry A ·
Journal of Materials Chemistry C · Applied Surface Science · Journal of Alloys and Compounds
（文献集中不属于上述期刊的文献归入 `其他期刊/`，哈工大博士论文归入 `学位论文/`）

## 目录与文件
- `分类文献库/<期刊名>/` —— 按期刊分类存储的 PDF 原文（共 48 个 PDF）
  - 已有文献集文件保留原文件名；联网新下载文件命名格式：`年份_第一作者_标题.pdf`
- `../文献清单.csv` —— 主清单：51 行（含 3 行重复文件标注），每行含分类、来源、年份、标题、作者、DOI、链接、本地PDF路径、备注
- `../未能下载_付费文献参考.csv` —— 54 篇近3年主题相关但无合法开放获取全文的文献（仅元数据+DOI，可经机构订阅获取）
- `../wenxian/`、`../wenxian.7z` —— 原始文献集（未改动，其中 3 组重复文件在分类库中只保留一份）

## 各分类统计
| 分类目录 | 已有文献集 | 联网新下载 | 付费墙(仅清单) |
|---|---|---|---|
| Journal of Electroanalytical Chemistry | 6 | 0 | 15 |
| Electrochimica Acta | 4 | 0 | 23 |
| ACS Omega | 2 | 2 | 0 |
| Colloids and Surfaces A | 2 | 0 | 4 |
| Chemical Engineering Journal | 1 | 0 | 1 |
| Small | 0 | 0 | 1 |
| ACS Applied Materials & Interfaces | 0 | 0 | 0 |
| Journal of Materials Chemistry A | 0 | 0 | 1 |
| Journal of Materials Chemistry C | 1 | 0 | 2 |
| Applied Surface Science | 1 | 0 | 4 |
| Journal of Alloys and Compounds | 0 | 0 | 3 |
| 其他期刊 | 28 | 0 | 0 |
| 学位论文 | 1 | 0 | 0 |
| **合计** | **46** | **2** | **54** |

## 检索与下载方式（全部为合法公开渠道）
- 元数据检索：Crossref API（主）、OpenAlex API（辅）
- OA 全文定位：Unpaywall、Semantic Scholar、Europe PMC、PMC Open Data (AWS S3)
- 已下载 PDF 均验证为有效文件（%PDF 魔数 + pdfinfo 页数），且均为开放获取版本（如 CC 许可）
- 未破解任何付费墙；Small / ACS AMI / JMCA / J. Alloys Compd 等刊近3年相关文献基本均为订阅制，
  故对应目录暂无新下载 PDF，相关文献已列入付费参考清单

## 备注
- `../_work/` 内为检索/整理过程的脚本与中间数据（candidates、日志等），可复核或删除
- 文献集中 3 组重复文件（同一文献两份拷贝）：分类库仅存一份，另一份在 CSV 备注中注明
