from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

DEFAULT_ACCOUNT_TYPES = [
    ("bank_account", "Bank Account"),
    ("mutual_fund", "Mutual Fund"),
    ("stocks", "Stocks"),
    ("pf", "PF"),
    ("lent", "Lent"),
    ("liquid_funds", "Liquid Funds"),
    ("other", "Other"),
]


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
        value = value.strip()
        if not value:
            raise ValueError("Type is required")
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
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Type is required")
        return value


class AccountOut(AccountBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    metrics: list[MetricOut] = []


class AccountTypeCreate(BaseModel):
    label: str

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Label is required")
        return value


class AccountTypeUpdate(BaseModel):
    label: str

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Label is required")
        return value


class AccountTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    value: str
    label: str


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


class AccountTypeProfitIn(BaseModel):
    account_type: str
    profit_percentage: Decimal


class AccountTypeProfitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_type: str
    date_of_entry: date
    profit_percentage: Decimal

    @field_serializer("profit_percentage")
    def serialize_profit_percentage(self, value: Decimal) -> float:
        return float(value)


class SnapshotCreate(BaseModel):
    date_of_entry: date
    accounts: list[SnapshotAccountPayload]
    account_type_profits: list[AccountTypeProfitIn] = Field(default_factory=list)


class AccountPrefillMetric(BaseModel):
    metric_id: int
    last_value: Decimal | None

    @field_serializer("last_value")
    def serialize_last_value(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class AccountPrefill(BaseModel):
    account_id: int
    last_current_value: Decimal | None
    metrics: list[AccountPrefillMetric]

    @field_serializer("last_current_value")
    def serialize_last_current_value(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class AccountTypeProfitPrefill(BaseModel):
    account_type: str
    last_profit_percentage: Decimal | None

    @field_serializer("last_profit_percentage")
    def serialize_last_profit_percentage(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class SnapshotPrefillResponse(BaseModel):
    accounts: list[AccountPrefill]
    account_type_profits: list[AccountTypeProfitPrefill]


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


class ForecastAccountTypeConfig(BaseModel):
    account_type: str
    current_value: float
    default_rate_percent: float
    has_profit_history: bool = False


class ForecastConfigResponse(BaseModel):
    account_types: list[ForecastAccountTypeConfig]
    default_inflation_rate: float = 6.0
    saved_inputs: dict | None = None


class ForecastAccountTypeInput(BaseModel):
    account_type: str
    monthly_sip: float
    rate_percent: float


class ForecastProjectionRequest(BaseModel):
    account_types: list[ForecastAccountTypeInput]
    step_up_percent: float = 0.0
    additional_investment: float = 0.0
    inflation_rate_percent: float = 6.0
    years: int = 10


class ForecastYearPoint(BaseModel):
    year: int
    calendar_year: int
    nominal_value: float
    real_value: float
    suggested_post_retirement_rate: float


class ForecastProjectionResponse(BaseModel):
    years: list[ForecastYearPoint]


class FirePlanRequest(BaseModel):
    retirement_year: int
    starting_corpus: float
    monthly_expense_today: float
    inflation_rate_percent: float
    post_retirement_growth_percent: float
    max_years: int = 100   # was 50


class FireYearRow(BaseModel):
    year: int
    monthly_swp: float
    total_value: float


class FirePlanResponse(BaseModel):
    starting_monthly_swp: float
    starting_corpus: float
    rows: list[FireYearRow]
    depleted_at_year: int | None
    sustainable: bool
