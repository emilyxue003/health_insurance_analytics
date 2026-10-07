WITH conditions_per_member AS (
    SELECT Member_ID, COUNT(DISTINCT Condition_ID) AS condition_count
    FROM MEMBER_CONDITION
    WHERE Diagnostic_date <= :as_of
    GROUP BY Member_ID
), claims_per_member AS (
    SELECT member_id, COUNT(*) AS claim_count, SUM(amount) AS claim_amount
    FROM CLAIMS
    WHERE date >= :claims_start AND date < :claims_end
    GROUP BY member_id
), member_costs AS (
    SELECT m.member_id, e.premium,
           COALESCE(d.condition_count, 0) AS condition_count,
           COALESCE(c.claim_count, 0) AS claim_count,
           COALESCE(c.claim_amount, 0) AS claim_amount
    FROM MEMBERS m
    JOIN ENROLLMENT e ON e.Enrollment_ID = m.Enrollment_ID
    LEFT JOIN conditions_per_member d ON d.Member_ID = m.member_id
    LEFT JOIN claims_per_member c ON c.member_id = m.member_id
    WHERE e.start_date <= :as_of
      AND (e.end_date IS NULL OR e.end_date >= :as_of)
      AND e.premium IS NOT NULL AND e.premium >= 0
)
SELECT CASE WHEN condition_count = 0 THEN '0'
            WHEN condition_count = 1 THEN '1'
            WHEN condition_count = 2 THEN '2' ELSE '3+' END AS conditions,
       COUNT(*) AS members,
       SUM(CASE WHEN claim_count > 0 THEN 1 ELSE 0 END) AS members_with_claims,
       SUM(claim_count) AS claims,
       ROUND(SUM(claim_amount), 2) AS total_claim_amount,
       ROUND(AVG(claim_amount), 2) AS average_claim_amount,
       ROUND(AVG(premium), 2) AS average_premium
FROM member_costs
GROUP BY CASE WHEN condition_count = 0 THEN '0'
              WHEN condition_count = 1 THEN '1'
              WHEN condition_count = 2 THEN '2' ELSE '3+' END
ORDER BY MIN(condition_count);
