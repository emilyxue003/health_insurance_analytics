WITH member_premiums AS (
    SELECT m.member_id, m.housing_insecurity,
           e.plan_id, e.Coverage_tier, e.premium
    FROM MEMBERS m
    JOIN ENROLLMENT e ON e.Enrollment_ID = m.Enrollment_ID
    WHERE e.start_date <= :as_of
      AND (e.end_date IS NULL OR e.end_date >= :as_of)
      AND e.premium IS NOT NULL AND e.premium >= 0
      AND m.housing_insecurity IN (0, 1)
), cells AS (
    SELECT plan_id, Coverage_tier,
           SUM(CASE WHEN housing_insecurity = 1 THEN 1 ELSE 0 END) AS yes_count,
           SUM(CASE WHEN housing_insecurity = 0 THEN 1 ELSE 0 END) AS no_count,
           AVG(CASE WHEN housing_insecurity = 1 THEN premium END) AS yes_premium,
           AVG(CASE WHEN housing_insecurity = 0 THEN premium END) AS no_premium
    FROM member_premiums
    GROUP BY plan_id, Coverage_tier
), comparable AS (
    SELECT *, CASE WHEN yes_count < no_count THEN yes_count ELSE no_count END AS cell_weight
    FROM cells
    WHERE yes_count > 0 AND no_count > 0
), standardized AS (
    SELECT COUNT(*) AS matched_cells,
           COALESCE(SUM(yes_count), 0) AS yes_members,
           COALESCE(SUM(no_count), 0) AS no_members,
           COALESCE(SUM(cell_weight), 0) AS overlap_weight,
           SUM(cell_weight * yes_premium) / NULLIF(SUM(cell_weight), 0) AS yes_premium,
           SUM(cell_weight * no_premium) / NULLIF(SUM(cell_weight), 0) AS no_premium
    FROM comparable
)
SELECT matched_cells, yes_members, no_members, overlap_weight,
       ROUND(yes_premium, 2) AS yes_premium,
       ROUND(no_premium, 2) AS no_premium,
       ROUND(yes_premium - no_premium, 2) AS premium_difference,
       ROUND(100.0 * (yes_premium - no_premium) / NULLIF(no_premium, 0), 2) AS difference_pct
FROM standardized;
