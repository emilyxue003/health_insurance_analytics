WITH cells AS (
    SELECT state, plan_id, Coverage_tier,
           COUNT(*) AS enrollments, SUM(premium) AS premium_total
    FROM ENROLLMENT
    WHERE start_date <= :as_of
      AND (end_date IS NULL OR end_date >= :as_of)
      AND premium IS NOT NULL AND premium >= 0
    GROUP BY state, plan_id, Coverage_tier
), peers AS (
    SELECT *,
           1.0 * SUM(premium_total) OVER (PARTITION BY plan_id, Coverage_tier)
             / NULLIF(SUM(enrollments) OVER (PARTITION BY plan_id, Coverage_tier), 0) AS peer_premium,
           SUM(enrollments) OVER (PARTITION BY plan_id, Coverage_tier) AS peer_count
    FROM cells
), states AS (
    SELECT state, SUM(enrollments) AS enrollments,
           ROUND(1.0 * SUM(premium_total) / SUM(enrollments), 2) AS average_premium,
           ROUND(SUM(100.0 * premium_total / peer_premium) / SUM(enrollments), 2) AS premium_index
    FROM peers
    WHERE peer_count >= :minimum_peers AND peer_premium > 0
    GROUP BY state
)
SELECT *, DENSE_RANK() OVER (ORDER BY premium_index DESC) AS index_rank
FROM states
ORDER BY premium_index DESC, state;
