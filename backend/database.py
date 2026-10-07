import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, URL
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv(Path(__file__).with_name('.env'))

required = ('DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DB_NAME')
missing = [name for name in required if not os.getenv(name)]
if missing:
    raise RuntimeError('Missing database settings: ' + ', '.join(missing) + '. Configure backend/.env using .env.example.')

SQLALCHEMY_DATABASE_URL = URL.create('mysql+pymysql', username=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'], host=os.environ['DB_HOST'],
    port=int(os.environ['DB_PORT']), database=os.environ['DB_NAME'])

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
