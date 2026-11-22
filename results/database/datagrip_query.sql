SELECT
    school,
    COUNT(*) AS records,
    SUM(planned_count) AS planned_count,
    COUNT(DISTINCT province) AS province_count
FROM admissions.admission_plan_v2
WHERE admission_year = 2026
GROUP BY school
UNION ALL
SELECT
    '合计' AS school,
    COUNT(*) AS records,
    SUM(planned_count) AS planned_count,
    COUNT(DISTINCT school) AS province_count
FROM admissions.admission_plan_v2
WHERE admission_year = 2026
ORDER BY CASE WHEN school = '合计' THEN 1 ELSE 0 END, records DESC;
