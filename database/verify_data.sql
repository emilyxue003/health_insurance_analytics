SELECT 'CONDITION' as Table_Name, COUNT(*) as Row_Count FROM health_insurance.CONDITION
UNION ALL
SELECT 'FACILITY', COUNT(*) FROM health_insurance.FACILITY
UNION ALL
SELECT 'INSURANCE', COUNT(*) FROM health_insurance.INSURANCE
UNION ALL
SELECT 'PLAN', COUNT(*) FROM health_insurance.PLAN
UNION ALL
SELECT 'ENROLLMENT', COUNT(*) FROM health_insurance.ENROLLMENT
UNION ALL
SELECT 'MEMBERS', COUNT(*) FROM health_insurance.MEMBERS
UNION ALL
SELECT 'MEMBER_CONDITION', COUNT(*) FROM health_insurance.MEMBER_CONDITION
UNION ALL
SELECT 'CLAIMS', COUNT(*) FROM health_insurance.CLAIMS;

SELECT * FROM health_insurance.MEMBERS LIMIT 10;
SELECT * FROM health_insurance.CLAIMS LIMIT 10;

SELECT 
    m.member_id, 
    m.State, 
    f.Name AS Primary_Care_Facility, 
    i.insurance_name AS Insurance_Provider
FROM health_insurance.MEMBERS m
JOIN health_insurance.FACILITY f ON m.Primary_Care_Facility_ID = f.Facility_ID
JOIN health_insurance.INSURANCE i ON m.Insurance_ID = i.insurance_id
LIMIT 20;
