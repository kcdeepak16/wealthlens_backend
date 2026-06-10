from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

VALID_ACCOUNT_TYPES = ["bank_account", "mutual_fund", "stocks", "pf", "lent", "other"]


class MetricBase(BaseModel):
    name: str
    is_percentage: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value


class MetricCreate(MetricBase):
    pass


class MetricUpdate(BaseModel):
    name: Optional[str] = None
    is_percentage: Optional[bool] = None


class MetricOut(MetricBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int


class AccountBase(BaseModel):
    name: str
    type: str
    date_of_start: date
    consider_for_networth: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in VALID_ACCOUNT_TYPES:
            raise ValueError(f"Type must be one of: {', '.join(VALID_ACCOUNT_TYPES)}")
        return value


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    date_of_start: Optional[date] = None
    consider_for_networth: Optional[bool] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in VALID_ACCOUNT_TYPES:
            raise ValueError(f"Type must be one of: {', '.join(VALID_ACCOUNT_TYPES)}")
        return value


class AccountOut(AccountBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    metrics: list[MetricOut] = []


class AccountWithStats(AccountOut):
    current_value: Optional[Decimal] = None
    previous_value: Optional[Decimal] = None
    change_absolute: Optional[Decimal] = None
    change_percent: Optional[float] = None
    sparkline: list[float] = []

    @field_serializer("current_value", "previous_value", "change_absolute")
    def serialize_optional_decimal(self, value: Optional[Decimal]) -> Optional[float]:
        return float(value) if value is not None else None


class MetricEntryIn(BaseModel):
    metric_id: int
    value: Decimal


class MetricEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    metric_id: int
    value: Decimal

    @field_serializer("value")
    def serialize_value(self, value: Decimal) -> float:
        return float(value)


class AccountEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    date_of_entry: date
    current_value: Decimal
    metric_entries: list[MetricEntryOut] = []

    @field_serializer("current_value")
    def serialize_current_value(self, value: Decimal) -> float:
        return float(value)


class SnapshotAccountPayload(BaseModel):
    account_id: int
    current_value: Decimal
    metric_entries: list[MetricEntryIn] = []


class SnapshotCreate(BaseModel):
    date_of_entry: date
    accounts: list[SnapshotAccountPayload]


class IndividualEntryCreate(BaseModel):
    date_of_entry: date
    current_value: Decimal
    metric_entries: list[MetricEntryIn] = []


class ChartDataPoint(BaseModel):
    date: date
    value: Optional[float] = None


class MetricChartSeries(BaseModel):
    metric_id: int
    metric_name: str
    is_percentage: bool
    data: list[ChartDataPoint]


class AccountChartData(BaseModel):
    value_series: list[ChartDataPoint]
    metric_series: list[MetricChartSeries]


class NetWorthPoint(BaseModel):
    date: date
    net_worth: float


class PortfolioBreakdownItem(BaseModel):
    type: str
    total_value: float
    percentage: float


class SummaryMetrics(BaseModel):
    monthly_growth_3m: Optional[float] = None
    best_performer_type: Optional[str] = None
    best_performer_pct: Optional[float] = None
    portfolio_age_days: Optional[int] = None
    entries_logged: int = 0
    avg_entry_gap_days: Optional[float] = None


class SummaryResponse(BaseModel):
    current_net_worth: float
    previous_net_worth: Optional[float] = None
    change_absolute: Optional[float] = None
    change_percent: Optional[float] = None
    last_entry_date: Optional[date] = None
    breakdown_by_type: list[PortfolioBreakdownItem]
    summary_metrics: SummaryMetrics
    excluded_accounts: list[AccountWithStats] = []
