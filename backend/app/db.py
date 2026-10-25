from typing import Generator
from sqlmodel import SQLModel, create_engine, Session
from backend.app.config import settings

# SQLite connection with connect_args for foreign keys and check_same_thread
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    # Automatic SQLite lightweight migration for new columns
    with engine.connect() as conn:
        try:
            cursor = conn.exec_driver_sql("PRAGMA table_info(application)")
            columns = [row[1] for row in cursor.fetchall()]
            if columns and "revision" not in columns:
                conn.exec_driver_sql("ALTER TABLE application ADD COLUMN revision INTEGER DEFAULT 1")
                conn.commit()
        except Exception as e:
            pass


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
