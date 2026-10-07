WITH eligible AS (
    SELECT Enrollment_ID, state, plan_id, Coverage_tier, premium
    FROM ENROLLMENT
    WHERE start_date <= :as_of
      AND (end_date IS NULL OR end_date >= :as_of)
      AND premium IS NOT NULL AND premium >= 0
), peers AS (
    SELECT *,
           AVG(premium) OVER (PARTITION BY plan_id, Coverage_tier) AS peer_premium,
           COUNT(*) OVER (PARTITION BY plan_id, Coverage_tier) AS peer_count
    FROM eligible
), states AS (
    SELECT state, COUNT(*) AS enrollments,
           ROUND(AVG(premium), 2) AS average_premium,
           ROUND(AVG(100.0 * premium / peer_premium), 2) AS premium_index
    FROM peers
    WHERE peer_count >= :minimum_peers AND peer_premium > 0
    GROUP BY state
)
SELECT *, DENSE_RANK() OVER (ORDER BY premium_index DESC) AS index_rank
FROM states
ORDER BY premium_index DESC, state;
