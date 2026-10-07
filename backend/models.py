from sqlalchemy import Column, Integer, String, Date, ForeignKey, Numeric, Enum, SmallInteger, Boolean, JSON
from sqlalchemy.orm import relationship
from database import Base

class Condition(Base):
    __tablename__ = "CONDITION"
    Condition_ID = Column(Integer, primary_key=True)
    Condition_name = Column(String(255))

class Facility(Base):
    __tablename__ = "FACILITY"
    Facility_ID = Column(Integer, primary_key=True)
    NPI = Column(String(10))
    Name = Column(String(255))
    State = Column(String(2))
    Contact_info = Column(JSON)

class Insurance(Base):
    __tablename__ = "INSURANCE"
    insurance_id = Column(Integer, primary_key=True)
    insurance_name = Column(String(255))
    contact_info = Column(JSON)

class Plan(Base):
    __tablename__ = "PLAN"
    plan_id = Column(Integer, primary_key=True)
    name = Column(String(255))
    insurance_id = Column(Integer, ForeignKey("INSURANCE.insurance_id"))
    base_rate = Column(Numeric(12, 2))
    deductable = Column(Numeric(12, 2))

class Enrollment(Base):
    __tablename__ = "ENROLLMENT"
    Enrollment_ID = Column(Integer, primary_key=True)
    Coverage_tier = Column(String(50))
    start_date = Column(Date)
    end_date = Column(Date)
    state = Column(String(2))
    plan_id = Column(Integer, ForeignKey("PLAN.plan_id"))
    premium = Column(Numeric(12, 2))

class Member(Base):
    __tablename__ = "MEMBERS"
    member_id = Column(Integer, primary_key=True, index=True)
    DOB = Column(Date)
    Sex = Column(Enum('F', 'M', 'O'))
    State = Column(String(2))
    Weight = Column(Numeric(6, 2))
    Height = Column(Numeric(5, 2))
    heart_rate = Column(SmallInteger)
    blood_pressure = Column(String(15))
    blood_oxygen = Column(SmallInteger)
    smoker = Column(Boolean)
    drinker = Column(Boolean)
    housing_insecurity = Column(Boolean)
    employment_status = Column(Boolean)
    hours_sleep_per_day = Column(Numeric(4, 1))
    minutes_exercise_per_week = Column(SmallInteger)
    
    # Foreign Keys
    Primary_Care_Facility_ID = Column(Integer, ForeignKey("FACILITY.Facility_ID"))
    Insurance_ID = Column(Integer, ForeignKey("INSURANCE.insurance_id"))
    Enrollment_ID = Column(Integer, ForeignKey("ENROLLMENT.Enrollment_ID"))

class MemberCondition(Base):
    __tablename__ = "MEMBER_CONDITION"
    Member_ID = Column(Integer, ForeignKey("MEMBERS.member_id"), primary_key=True)
    Condition_ID = Column(Integer, ForeignKey("CONDITION.Condition_ID"), primary_key=True)
    Diagnostic_date = Column(Date, primary_key=True)

class Claim(Base):
    __tablename__ = "CLAIMS"
    claim_id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("MEMBERS.member_id"))
    amount = Column(Numeric(12, 2))
    date = Column(Date)
    insurance_id = Column(Integer, ForeignKey("INSURANCE.insurance_id"))
