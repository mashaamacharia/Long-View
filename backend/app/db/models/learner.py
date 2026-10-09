from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Learner(Base):
    __tablename__ = "learners"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # e.g. "L1042"
    full_name: Mapped[str] = mapped_column(String(120))
    grade_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
