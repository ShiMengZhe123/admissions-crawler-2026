-- 五校招生计划汇总
SELECT school,
       COUNT(*) AS record_count,
       SUM(planned_count) AS planned_total
FROM admissions.admission_plan_v2
WHERE admission_year = 2026
GROUP BY school
ORDER BY school;

-- 每校各省记录数和计划人数
SELECT school, province,
       COUNT(*) AS record_count,
       SUM(planned_count) AS planned_total
FROM admissions.admission_plan_v2
WHERE admission_year = 2026
GROUP BY school, province
ORDER BY school, province;

-- 专业招生明细
SELECT admission_year, school, province, college_name,
       major_code, major_name, subject_type, batch_name,
       plan_type, planned_count, source_url, review_status
FROM admissions.admission_plan_v2
WHERE admission_year = 2026
ORDER BY school, province, major_name;

-- 空值/异常值检查
SELECT school,
       SUM(major_name IS NULL OR major_name = '') AS empty_major,
       SUM(province IS NULL OR province = '') AS empty_province,
       SUM(source_url IS NULL OR source_url = '') AS empty_source,
       SUM(planned_count IS NULL OR planned_count <= 0) AS invalid_count
FROM admissions.admission_plan_v2
WHERE admission_year = 2026
GROUP BY school
ORDER BY school;

-- 业务键重复检查
SELECT school, province, college_name, major_name,
       subject_type, batch_name, plan_type,
       selection_subject, COUNT(*) AS copies
FROM admissions.admission_plan_v2
WHERE admission_year = 2026
GROUP BY school, province, college_name, major_name,
         subject_type, batch_name, plan_type, selection_subject
HAVING COUNT(*) > 1
ORDER BY copies DESC, school, province;

-- OCR/人工核验状态
SELECT school, review_status,
       COUNT(*) AS record_count,
       SUM(planned_count) AS planned_total
FROM admissions.admission_plan_v2
WHERE admission_year = 2026
GROUP BY school, review_status
ORDER BY school, review_status;
