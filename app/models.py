from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    date_of_start = Column(Date, nullable=False)
    consider_for_networth = Column(Boolean, default=True, nullable=False)

    metrics = relationship("Metric", back_populates="account", cascade="all, delete-orphan")
    entries = relationship("AccountEntry", back_populates="account", cascade="all, delete-orphan")


class Metric(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    is_percentage = Column(Boolean, default=False, nullable=False)

    account = relationship("Account", back_populates="metrics")
    entries = relationship("MetricEntry", back_populates="metric", cascade="all, delete-orphan")


class AccountEntry(Base):
    __tablename__ = "account_entries"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    date_of_entry = Column(Date, nullable=False)
    current_value = Column(Numeric(15, 2), nullable=False)

    account = relationship("Account", back_populates="entries")
    metric_entries = relationship(
        "MetricEntry", back_populates="account_entry", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("account_id", "date_of_entry", name="uq_account_date"),)


class MetricEntry(Base):
    __tablename__ = "metric_entries"

    id = Column(Integer, primary_key=True, index=True)
    account_entry_id = Column(
        Integer, ForeignKey("account_entries.id", ondelete="CASCADE"), nullable=False
    )
    metric_id = Column(Integer, ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False)
    value = Column(Numeric(15, 4), nullable=False)

    account_entry = relationship("AccountEntry", back_populates="metric_entries")
    metric = relationship("Metric", back_populates="entries")
