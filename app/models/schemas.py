from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --- Enums ---

class TransportType(str, Enum):
    train = "train"
    flight = "flight"
    bus = "bus"


class PrimaryGoal(str, Enum):
    fastest = "fastest"
    cheapest = "cheapest"
    least_transfers = "least_transfers"
    comfort = "comfort"


class StatusEnum(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    error = "error"


# --- Domain Models ---

class Preferences(BaseModel):
    primary_goal: PrimaryGoal = PrimaryGoal.fastest
    mode_preference: list[TransportType] | None = None
    max_transfers: int | None = None
    avoid_night: bool = False
    avoid_long_layover: bool = False


class TravelRequest(BaseModel):
    response_id: str
    origin: str
    destination: str
    departure_date: str
    departure_time: str | None = None
    preferences: Preferences = Field(default_factory=Preferences)
    email: str = ""
    passenger_count: int = 1


class TransitOption(BaseModel):
    transport_type: TransportType
    provider: str = ""
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    price: float
    currency: str = "EUR"
    transfers: int = 0
    details: str = ""


class ScoredOption(BaseModel):
    option: TransitOption
    score: float
    score_explain: str = ""


class RecommendationResult(BaseModel):
    result_id: str
    response_id: str = ""
    origin: str
    destination: str
    transport_type: str
    provider: str = ""
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    price: float
    currency: str = "EUR"
    transfers: int = 0
    checkout_url: str = ""
    score_explain: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    original_request: TravelRequest | None = None


class ProcessingStatus(BaseModel):
    response_id: str
    status: StatusEnum = StatusEnum.pending
    result_id: str | None = None
    error_message: str | None = None


# --- Tally ---


class TallyField(BaseModel):
    key: str = ""
    label: str = ""
    type: str = ""
    value: Any = None


class TallySubmissionData(BaseModel):
    response_id: str = Field("", alias="responseId")
    submission_id: str = Field("", alias="submissionId")
    respondent_id: str = Field("", alias="respondentId")
    form_id: str = Field("", alias="formId")
    fields: list[TallyField] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class TallyWebhookPayload(BaseModel):
    event_id: str = Field("", alias="eventId")
    event_type: str = Field("", alias="eventType")
    created_at: str = Field("", alias="createdAt")
    data: TallySubmissionData = Field(default_factory=TallySubmissionData)

    model_config = {"populate_by_name": True}
