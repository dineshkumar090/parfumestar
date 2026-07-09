from sqlalchemy import Column, Integer, String, JSON
from app.database import Base

class SyncSchedule(Base):
    __tablename__ = "sync_schedules"

    id             = Column(Integer, primary_key=True, index=True)
    shop           = Column(String(255), unique=True, nullable=False, index=True)
    mode           = Column(String(20), default="manual")
    interval_value = Column(Integer, default=2)
    interval_unit  = Column(String(20), default="minutes")
    sync_types     = Column(JSON, default=["products", "pages", "blogs", "custom"])

    @property
    def interval_minutes(self) -> int:
        if self.interval_unit == "hours":
            return self.interval_value * 60
        if self.interval_unit == "days":
            return self.interval_value * 1440
        return self.interval_value

    def to_dict(self):
        return {
            "shop":             self.shop,
            "mode":             self.mode,
            "interval_value":   self.interval_value,
            "interval_unit":    self.interval_unit,
            "interval_minutes": self.interval_minutes,
            "sync_types":       self.sync_types or ["products", "pages", "blogs", "custom"],
        }