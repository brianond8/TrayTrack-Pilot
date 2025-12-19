from __future__ import annotations

from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Literal
import json
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, conint, validator
from sqlmodel import (
    SQLModel,
    Field as SAField,
    Session,
    create_engine,
    select,
    Relationship,
)


# =========================
# Enums & Constants
# =========================

class LocationType(str, Enum):
    hospital = "Hospital"
    warehouse = "Warehouse"
    vehicle = "Vehicle"
    office = "Office"
    home = "Home"
    storage = "Storage"
    other = "Other"


class TrayStatus(str, Enum):
    ready = "ready"
    in_location = "in_location"
    needs_restock = "needs_restock"


class RestockStatus(str, Enum):
    open = "open"
    closed = "closed"


COLOR_GREEN = "green"
COLOR_BLUE = "blue"
COLOR_YELLOW = "yellow"
COLOR_ORANGE = "orange"
COLOR_RED = "red"

USER_ID = "rep001"

# =========================
# DB Models
# =========================

class Tray(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    name: str = SAField(index=True, unique=True)
    status: TrayStatus = SAField(default=TrayStatus.ready)

    priority_numeric: Optional[int] = SAField(default=None, index=True)
    priority_partial: bool = SAField(default=False)
    color: str = SAField(default=COLOR_GREEN, index=True)

    last_seen_lat: Optional[float] = None
    last_seen_lng: Optional[float] = None
    last_seen_at: Optional[datetime] = SAField(default=None, index=True)
    last_location_type: Optional[LocationType] = None
    last_location_name: Optional[str] = None
    linked_case_id: Optional[str] = None

    

class TrayItem(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    tray_id: int = SAField(foreign_key="tray.id", index=True)
    sku: str = SAField(index=True)
    name: str
    is_critical: bool = SAField(default=False)
    qty_expected: Optional[int] = None
    qty_on_hand: Optional[int] = None

    
class RestockTask(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    tray_id: int = SAField(foreign_key="tray.id", index=True)
    status: RestockStatus = SAField(default=RestockStatus.open, index=True)
    created_at: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc), index=True)


    
class RestockTaskItem(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    task_id: int = SAField(foreign_key="restocktask.id", index=True)
    item_id: int = SAField(foreign_key="trayitem.id", index=True)
    qty_missing: Optional[int] = None
    reason: Optional[str] = None
    restocked: bool = SAField(default=False, index=True)
    restocked_at: Optional[datetime] = None
    restocked_by: Optional[str] = None

    
class Event(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    tray_id: int = SAField(foreign_key="tray.id", index=True)
    user_id: str
    type: str = SAField(index=True)
    timestamp: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc), index=True)
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    device_meta: Optional[str] = None

    location_type: Optional[LocationType] = None
    case_id: Optional[str] = None
    notes: Optional[str] = None
    payload_data: Optional[str] = None  # JSON string

class Case(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    user_id: str = SAField(index=True)
    procedure: str
    case_date: datetime = SAField(index=True)
    location: str
    doctor: Optional[str] = None
    tray_id: Optional[int] = SAField(default=None, foreign_key="tray.id")
    tray_other: Optional[str] = None  # For "other" tray option
    created_at: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc), index=True)
    notes: Optional[str] = None


class Doctor(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    user_id: str = SAField(index=True)
    name: str = SAField(index=True)
    specialty: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    hospital: Optional[str] = None
    created_at: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc), index=True)

class Note(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    user_id: str = SAField(index=True)
    title: str
    content: str
    created_at: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc), index=True)

class NotePin(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    note_id: int = SAField(foreign_key="note.id", index=True)
    entity_type: str = SAField(index=True)  # 'tray', 'case', 'doctor'
    entity_id: int = SAField(index=True)
    created_at: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc), index=True)

class Photo(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    user_id: str = SAField(index=True)
    entity_type: str = SAField(index=True)  # 'tray', 'case'
    entity_id: int = SAField(index=True)
    filename: str
    image_data: str  # Base64 encoded image
    caption: Optional[str] = None
    created_at: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc), index=True)



class StandaloneItem(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    user_id: str = SAField(index=True)
    name: str = SAField(index=True)
    item_type: str  # 'Cage', 'Biologic', 'Other'
    sku: Optional[str] = None
    status: TrayStatus = SAField(default=TrayStatus.ready)
    
    priority_numeric: Optional[int] = SAField(default=None, index=True)
    priority_partial: bool = SAField(default=False)
    color: str = SAField(default=COLOR_GREEN, index=True)
    
    qty_expected: Optional[int] = None
    qty_on_hand: Optional[int] = None
    is_critical: bool = SAField(default=False)
    
    last_seen_lat: Optional[float] = None
    last_seen_lng: Optional[float] = None
    last_seen_at: Optional[datetime] = SAField(default=None, index=True)
    last_location_type: Optional[LocationType] = None
    last_location_name: Optional[str] = None
    
    created_at: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc), index=True)

# =========================
# Pydantic Schemas
# =========================

class GPS(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class DropoffRequest(BaseModel):
    tray_id: int
    user_id: str
    gps: GPS
    location_type: LocationType
    location_name: Optional[str] = None
    case_id: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)
    device_meta: Optional[str] = None


class InventoryCheckItem(BaseModel):
    item_id: int
    reason: Optional[str] = Field(default=None, max_length=200)
    qty_missing: Optional[int] = Field(default=None, ge=0)
    qty_used: Optional[int] = Field(default=None, ge=0)

class InventoryCheckRequest(BaseModel):
    tray_id: int
    user_id: str
    gps: GPS
    items: list[InventoryCheckItem]

    has_assigned_case_within_72h: Optional[bool] = False
    case_count_per_week: Optional[float] = Field(default=0.0, ge=0)
    tray_avg_weekly: Optional[float] = Field(default=0.0, ge=0)
    any_critical_missing: Optional[bool] = False

    user_priority_numeric: Optional[conint(ge=1, le=3)] = None
    user_priority_partial: Optional[bool] = None

    location_type: Optional[LocationType] = None 
    location_name: Optional[str] = None  

class RestockFullRequest(BaseModel):
    tray_id: int
    user_id: str
    gps: GPS
    location_type: Optional[LocationType] = None
    location_name: Optional[str] = None
    device_meta: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class RestockPartialItem(BaseModel):
    item_id: int
    qty_restocked: Optional[int] = Field(default=None, ge=0)


class RestockPartialRequest(BaseModel):
    tray_id: int
    user_id: str
    gps: GPS
    items: list[RestockPartialItem]
    new_priority: Literal["partial", 1, 2, 3]
    location_type: Optional[LocationType] = None
    location_name: Optional[str] = None
    device_meta: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class TrayOutItem(BaseModel):
    id: int
    sku: str
    name: str
    is_critical: bool
    qty_expected: Optional[int]
    qty_on_hand: Optional[int]


class TrayOut(BaseModel):
    id: int
    name: str
    status: TrayStatus
    priority_numeric: Optional[int]
    priority_partial: bool
    color: str
    last_seen_lat: Optional[float]
    last_seen_lng: Optional[float]
    last_seen_at: Optional[datetime]
    last_location_type: Optional[LocationType]
    last_location_name: Optional[str]
    linked_case_id: Optional[str]
    items: list[TrayOutItem]


class CreateCaseIn(BaseModel):
    procedure: str = Field(min_length=1, max_length=200)
    case_date: datetime
    location: str = Field(min_length=1, max_length=200)
    doctor: Optional[str] = Field(default=None, max_length=200)
    tray_id: Optional[int] = None
    tray_other: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=500)


class CaseOut(BaseModel):
    id: int
    user_id: str
    procedure: str
    case_date: datetime
    location: str
    doctor: Optional[str]
    tray_id: Optional[int]
    tray_other: Optional[str]
    tray_name: Optional[str] = None  # Will populate from linked tray
    created_at: datetime
    notes: Optional[str]


class CreateDoctorIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    specialty: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=200)
    hospital: Optional[str] = Field(default=None, max_length=200)


class DoctorOut(BaseModel):
    id: int
    user_id: str
    name: str
    specialty: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    hospital: Optional[str]
    created_at: datetime
    updated_at: datetime


class CreateNoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    pin_to_trays: Optional[list[int]] = Field(default=None)
    pin_to_standalone: Optional[list[int]] = Field(default=None)
    pin_to_cases: Optional[list[int]] = Field(default=None)
    pin_to_doctors: Optional[list[int]] = Field(default=None)


class UpdateNoteIn(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1)


class NotePinOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    entity_name: Optional[str] = None  # Will be populated with tray/case/doctor name


class NoteOut(BaseModel):
    id: int
    user_id: str
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
    pins: list[NotePinOut] = []

class StandaloneItemOut(BaseModel):
    id: int
    user_id: str
    name: str
    item_type: str
    sku: Optional[str]
    status: TrayStatus
    priority_numeric: Optional[int]
    priority_partial: bool
    color: str
    qty_expected: Optional[int]
    qty_on_hand: Optional[int]
    is_critical: bool
    last_seen_lat: Optional[float]
    last_seen_lng: Optional[float]
    last_seen_at: Optional[datetime]
    last_location_type: Optional[LocationType]
    last_location_name: Optional[str]
    created_at: datetime


class CreateStandaloneItemIn(BaseModel):
    item_type: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    sku: Optional[str] = Field(default=None, max_length=50)
    qty_expected: Optional[int] = Field(default=None, ge=0)
    qty_on_hand: Optional[int] = Field(default=None, ge=0)
    is_critical: bool = False

class PhotoOut(BaseModel):
    id: int
    user_id: str
    entity_type: str
    entity_id: int
    filename: str
    image_data: str
    caption: Optional[str]
    created_at: datetime


class UploadPhotoIn(BaseModel):
    entity_type: str = Field(pattern="^(tray|case|standalone)$")
    entity_id: int
    filename: str
    image_data: str  # Base64 encoded
    caption: Optional[str] = Field(default=None, max_length=200)


# =========================
# Priority & Color Logic
# =========================

def map_color(priority_numeric: Optional[int], partial: bool, ready: bool) -> str:
    if ready:
        return COLOR_GREEN
    if priority_numeric is not None:
        if priority_numeric == 1:
            return COLOR_RED
        if priority_numeric == 2:
            return COLOR_ORANGE
        if priority_numeric == 3:
            return COLOR_YELLOW
    if partial:
        return COLOR_BLUE
    return COLOR_GREEN


def apply_priority_non_downgrade(
    existing_numeric: Optional[int],
    existing_partial: bool,
    new_numeric: Optional[int],
    new_partial: Optional[bool]
) -> tuple[Optional[int], bool]:
    out_numeric = existing_numeric
    out_partial = existing_partial

    if new_numeric is not None:
        if out_numeric is None or new_numeric > out_numeric:
            out_numeric = new_numeric

    if new_partial:
        if out_numeric is None:
            out_partial = True

    return out_numeric, out_partial


def auto_escalation_suggestion(
    has_assigned_case_within_72h: bool = False,
    case_count_per_week: float = 0.0,
    tray_avg_weekly: float = 0.0,
    any_critical_missing: bool = False
) -> Optional[int]:
    points = 0
    if case_count_per_week > tray_avg_weekly:
        points += 1
    if has_assigned_case_within_72h:
        points += 1
    if any_critical_missing:
        points += 1

    if points >= 3:
        return 3
    if points == 2:
        return 2
    if points == 1:
        return 1
    return None


# =========================
# App Setup
# =========================

import os

app = FastAPI(title="CaseFlow AI - Tray Management API")

ALLOWED_ORIGINS = [
    "https://traytrack-pilot-1.onrender.com",
    "http://localhost:3000",
    "http://127.0.0.1:5500",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)





from sqlalchemy.pool import StaticPool

# Use environment variable for database path in production
DB_PATH = os.getenv("DATABASE_PATH", "caseflow.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
SQLModel.metadata.create_all(engine)

# =========================
# USER MANAGEMENT
# =========================

class User(SQLModel, table=True):
    id: Optional[int] = SAField(default=None, primary_key=True)
    username: str = SAField(index=True, unique=True)
    display_name: str
    created_at: datetime = SAField(default_factory=lambda: datetime.now(timezone.utc))
    last_active: Optional[datetime] = None

class UserCreate(BaseModel):
    username: str
    display_name: str

@app.post("/users/login")
def login_user(user_data: UserCreate):
    """Login or create user - no password for pilot"""
    with Session(engine) as session:
        # Check if user exists
        existing = session.exec(
            select(User).where(User.username == user_data.username.lower())
        ).first()
        
        if existing:
            # Update last active
            existing.last_active = datetime.now(timezone.utc)
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing
        
        # Create new user
        new_user = User(
            username=user_data.username.lower(),
            display_name=user_data.display_name,
            last_active=datetime.now(timezone.utc)
        )
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        return new_user

@app.get("/users/current/{username}")
def get_current_user(username: str):
    """Get user by username"""
    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.username == username.lower())
        ).first()
        if not user:
            raise HTTPException(404, "User not found")
        return user

# =========================
# Helper Functions
# =========================

def get_tray_or_404(session: Session, tray_id: int) -> Tray:
    tray = session.get(Tray, tray_id)
    if not tray:
        raise HTTPException(404, f"Tray {tray_id} not found")
    return tray


def ensure_open_restock_task(session: Session, tray_id: int) -> RestockTask:
    task = session.exec(
        select(RestockTask).where(
            RestockTask.tray_id == tray_id,
            RestockTask.status == RestockStatus.open,
        )
    ).first()
    if not task:
        task = RestockTask(tray_id=tray_id, status=RestockStatus.open)
        session.add(task)
        session.flush()  # Flush instead of commit to avoid race conditions
        session.refresh(task)
    return task


def close_restock_task_if_empty(session: Session, tray_id: int):
    task = session.exec(
        select(RestockTask).where(
            RestockTask.tray_id == tray_id,
            RestockTask.status == RestockStatus.open,
        )
    ).first()
    if not task:
        return
    open_items = session.exec(
        select(RestockTaskItem).where(
            RestockTaskItem.task_id == task.id,
            RestockTaskItem.restocked == False,
        )
    ).all()
    if not open_items:
        task.status = RestockStatus.closed
        task.updated_at = datetime.now(timezone.utc)
        session.add(task)
        session.commit()


def tray_to_out(session: Session, tray: Tray) -> TrayOut:
    items = session.exec(select(TrayItem).where(TrayItem.tray_id == tray.id)).all()
    out_items = [
        TrayOutItem(
            id=i.id,
            sku=i.sku,
            name=i.name,
            is_critical=i.is_critical,
            qty_expected=i.qty_expected,
            qty_on_hand=i.qty_on_hand,
        )
        for i in items
    ]
    return TrayOut(
        id=tray.id,
        name=tray.name,
        status=tray.status,
        priority_numeric=tray.priority_numeric,
        priority_partial=tray.priority_partial,
        color=tray.color,
        last_seen_lat=tray.last_seen_lat,
        last_seen_lng=tray.last_seen_lng,
        last_seen_at=tray.last_seen_at,
        last_location_type=tray.last_location_type,
        last_location_name=tray.last_location_name,
        linked_case_id=tray.linked_case_id,
        items=out_items,
    )


# =========================
# Endpoints
# =========================

@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "deploy_stamp": "cors_fix_1",  # change this string every deploy
    }



@app.get("/metadata/location-types")
def list_location_types():
    ordered = [lt.value for lt in LocationType]
    return {"location_types": ordered}


# Seed endpoints
class CreateTrayIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@app.post("/seed/trays", response_model=TrayOut)
def create_tray(payload: CreateTrayIn):
    try:
        with Session(engine) as session:
            existing = session.exec(select(Tray).where(Tray.name == payload.name)).first()
            if existing:
                raise HTTPException(400, f"Tray '{payload.name}' already exists")
            
            tray = Tray(name=payload.name)
            tray.color = map_color(tray.priority_numeric, tray.priority_partial, tray.status == TrayStatus.ready)
            session.add(tray)
            session.commit()
            session.refresh(tray)
            return tray_to_out(session, tray)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to create tray: {str(e)}")


class CreateTrayItemIn(BaseModel):
    tray_id: int
    sku: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    is_critical: bool = False
    qty_expected: Optional[int] = Field(default=None, ge=0)
    qty_on_hand: Optional[int] = Field(default=None, ge=0)


@app.post("/seed/tray-items", response_model=TrayOut)
def create_tray_item(payload: CreateTrayItemIn):
    try:
        with Session(engine) as session:
            tray = get_tray_or_404(session, payload.tray_id)
            
            existing = session.exec(
                select(TrayItem).where(
                    TrayItem.tray_id == payload.tray_id,
                    TrayItem.sku == payload.sku
                )
            ).first()
            if existing:
                raise HTTPException(400, f"Item with SKU '{payload.sku}' already exists in this tray")
            
            item = TrayItem(
                tray_id=payload.tray_id,
                sku=payload.sku,
                name=payload.name,
                is_critical=payload.is_critical,
                qty_expected=payload.qty_expected,
                qty_on_hand=payload.qty_on_hand,
            )
            session.add(item)
            session.commit()
            session.refresh(tray)
            return tray_to_out(session, tray)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to create tray item: {str(e)}")

@app.get("/trays/{tray_id}", response_model=TrayOut)
def get_tray(tray_id: int):
    with Session(engine) as session:
        tray = get_tray_or_404(session, tray_id)
        return tray_to_out(session, tray)


@app.get("/trays", response_model=list[TrayOut])
def list_trays(
    sort: Literal["priority", "name"] = Query("priority"),
    limit: Optional[int] = Query(None, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    with Session(engine) as session:
        trays = session.exec(select(Tray)).all()
        prio_rank = {COLOR_RED: 0, COLOR_ORANGE: 1, COLOR_YELLOW: 2, COLOR_BLUE: 3, COLOR_GREEN: 4}
        if sort == "priority":
            trays.sort(key=lambda t: prio_rank.get(t.color, 5))
        else:
            trays.sort(key=lambda t: t.name.lower())
        
        # Apply pagination
        if limit:
            trays = trays[offset:offset + limit]
        elif offset > 0:
            trays = trays[offset:]
            
        return [tray_to_out(session, t) for t in trays]


@app.post("/scan-events/dropoff")
def log_dropoff(payload: DropoffRequest):
    try:
        with Session(engine) as session:
            tray = get_tray_or_404(session, payload.tray_id)

            evt = Event(
            tray_id=tray.id,
            user_id=payload.user_id,
            type="dropoff",
            timestamp=datetime.now(timezone.utc),
            gps_lat=payload.gps.lat,
            gps_lng=payload.gps.lng,
            device_meta=payload.device_meta,
            location_type=payload.location_type,
            case_id=payload.case_id,
            notes=payload.notes,
        )
        session.add(evt)

        tray.status = TrayStatus.in_location
        tray.last_seen_lat = payload.gps.lat
        tray.last_seen_lng = payload.gps.lng
        tray.last_seen_at = evt.timestamp
        tray.last_location_type = payload.location_type
        tray.last_location_name = payload.location_name
        if payload.case_id:
            tray.linked_case_id = payload.case_id

        tray.color = map_color(tray.priority_numeric, tray.priority_partial, tray.status == TrayStatus.ready)

        session.add(tray)
        session.commit()
        return {"ok": True, "event_id": evt.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to log dropoff: {str(e)}")


@app.post("/inventory-checks")
def inventory_check(payload: InventoryCheckRequest):
    try:
        with Session(engine) as session:
            tray = get_tray_or_404(session, payload.tray_id)

            if not payload.items:
                raise HTTPException(400, "Must specify at least one item needing restock")

            task = ensure_open_restock_task(session, tray.id)

            for it in payload.items:
                item = session.get(TrayItem, it.item_id)
                if not item or item.tray_id != tray.id:
                    raise HTTPException(400, f"Item {it.item_id} not found in tray {tray.id}")

                # Update qty_on_hand based on qty_used
                if it.qty_used is not None and it.qty_used > 0:
                    current_qty = item.qty_on_hand or 0
                    item.qty_on_hand = max(0, current_qty - it.qty_used)
                    session.add(item)

                existing = session.exec(
                    select(RestockTaskItem).where(
                        RestockTaskItem.task_id == task.id,
                        RestockTaskItem.item_id == it.item_id,
                        RestockTaskItem.restocked == False,
                    )
                ).first()
                if not existing:
                    rti = RestockTaskItem(
                        task_id=task.id,
                        item_id=it.item_id,
                        qty_missing=it.qty_missing,
                        reason=it.reason,
                        restocked=False,
                    )
                    session.add(rti)
                else:
                    if it.reason is not None:
                        existing.reason = it.reason
                    if it.qty_missing is not None:
                        existing.qty_missing = it.qty_missing
                    session.add(existing)

            evt = Event(
                tray_id=tray.id,
                user_id=payload.user_id,
                type="inventory_check",
                gps_lat=payload.gps.lat,
                gps_lng=payload.gps.lng,
                payload_data=json.dumps({"items_flagged": [i.item_id for i in payload.items]}),
            )
            session.add(evt)

            tray.status = TrayStatus.needs_restock

            # Update GPS tracking
            tray.last_seen_lat = payload.gps.lat
            tray.last_seen_lng = payload.gps.lng
            tray.last_seen_at = datetime.now(timezone.utc)

            auto_suggest = auto_escalation_suggestion(
                has_assigned_case_within_72h=payload.has_assigned_case_within_72h or False,
                case_count_per_week=payload.case_count_per_week or 0.0,
                tray_avg_weekly=payload.tray_avg_weekly or 0.0,
                any_critical_missing=payload.any_critical_missing or False,
            )

            new_num = payload.user_priority_numeric if payload.user_priority_numeric is not None else auto_suggest
            new_partial = bool(payload.user_priority_partial) if payload.user_priority_partial is not None else False

            tray.priority_numeric, tray.priority_partial = apply_priority_non_downgrade(
                existing_numeric=tray.priority_numeric,
                existing_partial=tray.priority_partial,
                new_numeric=new_num,
                new_partial=new_partial,
            )

            tray.color = map_color(tray.priority_numeric, tray.priority_partial, tray.status == TrayStatus.ready)

            if payload.location_type:
                tray.last_location_type = payload.location_type
                tray.last_location_name = payload.location_name

            task.updated_at = datetime.now(timezone.utc)

            session.add(tray)
            session.add(task)
            session.commit()
            return {"ok": True, "tray": tray_to_out(session, tray)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to perform inventory check: {str(e)}")


@app.post("/restocks/full")
def restock_full(payload: RestockFullRequest):
    try:
        with Session(engine) as session:
            tray = get_tray_or_404(session, payload.tray_id)

            # Reset all items to their expected quantities
            items = session.exec(select(TrayItem).where(TrayItem.tray_id == tray.id)).all()
            for item in items:
                if item.qty_expected is not None:
                    item.qty_on_hand = item.qty_expected
                    session.add(item)

            task = session.exec(
                select(RestockTask).where(RestockTask.tray_id == tray.id, RestockTask.status == RestockStatus.open)
            ).first()
            if task:
                open_items = session.exec(
                    select(RestockTaskItem).where(RestockTaskItem.task_id == task.id, RestockTaskItem.restocked == False)
                ).all()
                for oi in open_items:
                    oi.restocked = True
                    oi.restocked_at = datetime.now(timezone.utc)
                    oi.restocked_by = payload.user_id
                    session.add(oi)
                task.status = RestockStatus.closed
                task.updated_at = datetime.now(timezone.utc)
                session.add(task)

            evt = Event(
                tray_id=tray.id,
                user_id=payload.user_id,
                type="restock_full",
                gps_lat=payload.gps.lat,
                gps_lng=payload.gps.lng,
                device_meta=payload.device_meta,
                notes=payload.notes,
            )
            session.add(evt)

            tray.status = TrayStatus.ready
            tray.priority_numeric = None
            tray.priority_partial = False
            tray.color = map_color(tray.priority_numeric, tray.priority_partial, ready=True)

            if payload.location_type:
                tray.last_location_type = payload.location_type
                tray.last_location_name = payload.location_name
                tray.last_seen_at = datetime.now(timezone.utc)

            session.add(tray)
            session.commit()
            return {"ok": True, "tray": tray_to_out(session, tray)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to perform full restock: {str(e)}")

@app.post("/restocks/partial")
def restock_partial(payload: RestockPartialRequest):
    try:
        with Session(engine) as session:
            tray = get_tray_or_404(session, payload.tray_id)

            if not payload.items:
                raise HTTPException(400, "Must specify at least one item to restock")

            task = ensure_open_restock_task(session, tray.id)

            by_id = {p.item_id: p for p in payload.items}
            open_items = session.exec(
                select(RestockTaskItem).where(RestockTaskItem.task_id == task.id, RestockTaskItem.restocked == False)
            ).all()

            # Update qty_on_hand for restocked items
            for item_payload in payload.items:
                item = session.get(TrayItem, item_payload.item_id)
                if item and item.tray_id == tray.id:
                    if item_payload.qty_restocked is not None and item_payload.qty_restocked > 0:
                        current_qty = item.qty_on_hand or 0
                        # Add restocked quantity, but don't exceed expected quantity
                        if item.qty_expected is not None:
                            item.qty_on_hand = min(current_qty + item_payload.qty_restocked, item.qty_expected)
                        else:
                            item.qty_on_hand = current_qty + item_payload.qty_restocked
                        session.add(item)

            for oi in open_items:
                sel = by_id.get(oi.item_id)
                if sel:
                    oi.restocked = True
                    oi.restocked_at = datetime.now(timezone.utc)
                    oi.restocked_by = payload.user_id
                    if sel.qty_restocked is not None:
                        oi.qty_missing = max(0, (oi.qty_missing or 0) - sel.qty_restocked)
                    session.add(oi)

            remaining_open = session.exec(
                select(RestockTaskItem).where(RestockTaskItem.task_id == task.id, RestockTaskItem.restocked == False)
            ).all()

            evt = Event(
                tray_id=tray.id,
                user_id=payload.user_id,
                type="restock_partial",
                gps_lat=payload.gps.lat,
                gps_lng=payload.gps.lng,
                device_meta=payload.device_meta,
                notes=payload.notes,
                payload_data=json.dumps({"restocked_items": [p.item_id for p in payload.items]}),
            )
            session.add(evt)

            if remaining_open:
                tray.status = TrayStatus.needs_restock
            else:
                tray.status = TrayStatus.ready

            if payload.new_priority == "partial":
                new_num = None
                new_partial = True if remaining_open else False
            else:
                new_num = int(payload.new_priority)
                new_partial = False

            tray.priority_numeric = new_num
            tray.priority_partial = new_partial
           
            # Update color based on current status
            tray.color = map_color(
                tray.priority_numeric, 
                tray.priority_partial, 
                tray.status == TrayStatus.ready
            )

            if payload.location_type:
                tray.last_location_type = payload.location_type
                tray.last_location_name = payload.location_name
                tray.last_seen_at = datetime.now(timezone.utc)

            close_restock_task_if_empty(session, tray.id)

            session.add(tray)
            session.commit()
            return {"ok": True, "tray": tray_to_out(session, tray)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to perform partial restock: {str(e)}")

@app.post("/cases", response_model=CaseOut)
def create_case(payload: CreateCaseIn):
    try:
        with Session(engine) as session:
            case = Case(
            user_id=USER_ID,
            procedure=payload.procedure,
            case_date=payload.case_date,
            location=payload.location,
            doctor=payload.doctor,
            tray_id=payload.tray_id,
            tray_other=payload.tray_other,
            notes=payload.notes,
        )
        session.add(case)
        session.commit()
        session.refresh(case)
        
        tray_name = None
        if case.tray_id:
            tray = session.get(Tray, case.tray_id)
            if tray:
                tray_name = tray.name
        
        return CaseOut(
            id=case.id,
            user_id=case.user_id,
            procedure=case.procedure,
            case_date=case.case_date,
            location=case.location,
            doctor=case.doctor,
            tray_id=case.tray_id,
            tray_other=case.tray_other,
            tray_name=tray_name,
            created_at=case.created_at,
            notes=case.notes,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to create case: {str(e)}")


@app.get("/cases", response_model=list[CaseOut])
def list_cases(
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    limit: Optional[int] = Query(None, ge=1, le=1000),
    offset: Optional[int] = Query(0, ge=0)
):
    try:
        with Session(engine) as session:
            query = select(Case).where(Case.user_id == USER_ID)
            
            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date)
                    query = query.where(Case.case_date >= start_dt)
                except ValueError:
                    raise HTTPException(400, f"Invalid start_date format: {start_date}")
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date)
                    query = query.where(Case.case_date <= end_dt)
                except ValueError:
                    raise HTTPException(400, f"Invalid end_date format: {end_date}")
        
        query = query.order_by(Case.case_date)
        cases = session.exec(query).all()
        
        result = []
        for case in cases:
            tray_name = None
            if case.tray_id:
                tray = session.get(Tray, case.tray_id)
                if tray:
                    tray_name = tray.name
            
            result.append(CaseOut(
                id=case.id,
                user_id=case.user_id,
                procedure=case.procedure,
                case_date=case.case_date,
                location=case.location,
                doctor=case.doctor,
                tray_id=case.tray_id,
                tray_other=case.tray_other,
                tray_name=tray_name,
                created_at=case.created_at,
                notes=case.notes,
            ))
        
        # Apply pagination
        if limit:
            result = result[offset:offset + limit]
        elif offset > 0:
            result = result[offset:]
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to list cases: {str(e)}")


@app.delete("/cases/{case_id}")
def delete_case(case_id: int):
    try:
        with Session(engine) as session:
            case = session.get(Case, case_id)
            if not case or case.user_id != USER_ID:
                raise HTTPException(404, "Case not found")
            
            # Delete all note pins associated with this case
            pins = session.exec(
                select(NotePin).where(
                    NotePin.entity_type == "case",
                    NotePin.entity_id == case_id
                )
            ).all()
            for pin in pins:
                session.delete(pin)
            
            session.delete(case)
            session.commit()
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to delete case: {str(e)}")
    
@app.put("/cases/{case_id}", response_model=CaseOut)
def update_case(case_id: int, payload: CreateCaseIn):
    try:
        with Session(engine) as session:
            case = session.get(Case, case_id)
        if not case or case.user_id != USER_ID:
            raise HTTPException(404, "Case not found")

        case.procedure = payload.procedure
        case.case_date = payload.case_date
        case.location = payload.location
        case.doctor = payload.doctor
        case.tray_id = payload.tray_id
        case.tray_other = payload.tray_other
        case.notes = payload.notes

        session.add(case)
        session.commit()
        session.refresh(case)

        tray_name = None
        if case.tray_id:
            tray = session.get(Tray, case.tray_id)
            if tray:
             tray_name = tray.name

        return CaseOut(
            id=case.id,
            user_id=case.user_id,
            procedure=case.procedure,
            case_date=case.case_date,
            location=case.location,
            doctor=case.doctor,
            tray_id=case.tray_id,
            tray_other=case.tray_other,
            tray_name=tray_name,
            created_at=case.created_at,
            notes=case.notes,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to update case: {str(e)}")


# =========================
# Doctor Endpoints
# =========================

@app.post("/doctors", response_model=DoctorOut)
def create_doctor(payload: CreateDoctorIn):
    try:
        with Session(engine) as session:
            doctor = Doctor(
                user_id=USER_ID,
                name=payload.name,
                specialty=payload.specialty,
                phone=payload.phone,
                email=payload.email,
                hospital=payload.hospital,
            )
            session.add(doctor)
            session.commit()
            session.refresh(doctor)
            return doctor
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to create doctor: {str(e)}")


@app.get("/doctors", response_model=list[DoctorOut])
def list_doctors():
    with Session(engine) as session:
        doctors = session.exec(
            select(Doctor).where(Doctor.user_id == USER_ID).order_by(Doctor.name)
        ).all()
        return doctors


@app.get("/doctors/{doctor_id}", response_model=DoctorOut)
def get_doctor(doctor_id: int):
    with Session(engine) as session:
        doctor = session.get(Doctor, doctor_id)
        if not doctor or doctor.user_id != USER_ID:
            raise HTTPException(404, "Doctor not found")
        return doctor


@app.put("/doctors/{doctor_id}", response_model=DoctorOut)
def update_doctor(doctor_id: int, payload: CreateDoctorIn):
    try:
        with Session(engine) as session:
            doctor = session.get(Doctor, doctor_id)
            if not doctor or doctor.user_id != USER_ID:
                raise HTTPException(404, "Doctor not found")

            doctor.name = payload.name
            doctor.specialty = payload.specialty
            doctor.phone = payload.phone
            doctor.email = payload.email
            doctor.hospital = payload.hospital
            doctor.updated_at = datetime.now(timezone.utc)

            session.add(doctor)
            session.commit()
            session.refresh(doctor)
            return doctor
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to update doctor: {str(e)}")


@app.delete("/doctors/{doctor_id}")
def delete_doctor(doctor_id: int):
    try:
        with Session(engine) as session:
            doctor = session.get(Doctor, doctor_id)
        if not doctor or doctor.user_id != USER_ID:
            raise HTTPException(404, "Doctor not found")

        # Delete all note pins associated with this doctor
        pins = session.exec(
            select(NotePin).where(
                NotePin.entity_type == "doctor",
                NotePin.entity_id == doctor_id
            )
        ).all()
        for pin in pins:
            session.delete(pin)

            session.delete(doctor)
            session.commit()
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to delete doctor: {str(e)}")


# =========================
# Note Endpoints
# =========================

def note_to_out(session: Session, note: Note) -> NoteOut:
    """Convert a Note model to NoteOut with populated pins"""
    pins = session.exec(
        select(NotePin).where(NotePin.note_id == note.id)
    ).all()

    pin_outs = []
    for pin in pins:
        entity_name = None
        if pin.entity_type == "tray":
            tray = session.get(Tray, pin.entity_id)
            if tray:
                entity_name = tray.name
        elif pin.entity_type == "case":
            case = session.get(Case, pin.entity_id)
            if case:
                entity_name = f"{case.procedure} - {case.case_date.strftime('%m/%d/%Y')}"
        elif pin.entity_type == "doctor":
            doctor = session.get(Doctor, pin.entity_id)
            if doctor:
                entity_name = doctor.name
        elif pin.entity_type == "standalone":
            item = session.get(StandaloneItem, pin.entity_id)
            if item:
                entity_name = item.name

        pin_outs.append(NotePinOut(
            id=pin.id,
            entity_type=pin.entity_type,
            entity_id=pin.entity_id,
            entity_name=entity_name
        ))

    return NoteOut(
        id=note.id,
        user_id=note.user_id,
        title=note.title,
        content=note.content,
        created_at=note.created_at,
        updated_at=note.updated_at,
        pins=pin_outs
    )


@app.post("/notes", response_model=NoteOut)
def create_note(payload: CreateNoteIn):
    try:
        with Session(engine) as session:
            note = Note(
            user_id=USER_ID,
            title=payload.title,
            content=payload.content,
        )
        session.add(note)
        session.commit()
        session.refresh(note)

        # Add pins
        if payload.pin_to_trays:
            for tray_id in payload.pin_to_trays:
                pin = NotePin(note_id=note.id, entity_type="tray", entity_id=tray_id)
                session.add(pin)

        if payload.pin_to_standalone:
            for item_id in payload.pin_to_standalone:
                pin = NotePin(note_id=note.id, entity_type="standalone", entity_id=item_id)
                session.add(pin)

        if payload.pin_to_cases:
            for case_id in payload.pin_to_cases:
                pin = NotePin(note_id=note.id, entity_type="case", entity_id=case_id)
                session.add(pin)

        if payload.pin_to_doctors:
            for doctor_id in payload.pin_to_doctors:
                pin = NotePin(note_id=note.id, entity_type="doctor", entity_id=doctor_id)
                session.add(pin)

        session.commit()
        return note_to_out(session, note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to create note: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Failed to create note: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to create note: {str(e)}")


@app.get("/notes", response_model=list[NoteOut])
def list_notes():
    with Session(engine) as session:
        notes = session.exec(
            select(Note).where(Note.user_id == USER_ID).order_by(Note.updated_at.desc())
        ).all()
        return [note_to_out(session, note) for note in notes]


@app.get("/notes/{note_id}", response_model=NoteOut)
def get_note(note_id: int):
    with Session(engine) as session:
        note = session.get(Note, note_id)
        if not note or note.user_id != USER_ID:
            raise HTTPException(404, "Note not found")
        return note_to_out(session, note)


@app.put("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: int, payload: UpdateNoteIn):
    try:
        with Session(engine) as session:
            note = session.get(Note, note_id)
            if not note or note.user_id != USER_ID:
                raise HTTPException(404, "Note not found")

            if payload.title is not None:
                note.title = payload.title
            if payload.content is not None:
                note.content = payload.content
            note.updated_at = datetime.now(timezone.utc)

            session.add(note)
            session.commit()
            session.refresh(note)
            return note_to_out(session, note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to update note: {str(e)}")


@app.delete("/notes/{note_id}")
def delete_note(note_id: int):
    try:
        with Session(engine) as session:
            note = session.get(Note, note_id)
            if not note or note.user_id != USER_ID:
                raise HTTPException(404, "Note not found")

            # Delete all pins associated with this note
            pins = session.exec(select(NotePin).where(NotePin.note_id == note_id)).all()
            for pin in pins:
                session.delete(pin)

            session.delete(note)
            session.commit()
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to delete note: {str(e)}")


class PinNoteRequest(BaseModel):
    entity_type: Literal["tray", "case", "doctor", "standalone"]
    entity_id: int


@app.post("/notes/{note_id}/pin", response_model=NoteOut)
def pin_note(note_id: int, payload: PinNoteRequest):
    try:
        with Session(engine) as session:
            note = session.get(Note, note_id)
            if not note or note.user_id != USER_ID:
                raise HTTPException(404, "Note not found")

            # Check if already pinned
            existing = session.exec(
                select(NotePin).where(
                    NotePin.note_id == note_id,
                    NotePin.entity_type == payload.entity_type,
                    NotePin.entity_id == payload.entity_id
                )
            ).first()

            if existing:
                raise HTTPException(400, "Note already pinned to this entity")

            pin = NotePin(
                note_id=note_id,
                entity_type=payload.entity_type,
                entity_id=payload.entity_id
            )
            session.add(pin)
            session.commit()

            return note_to_out(session, note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to pin note: {str(e)}")


@app.delete("/notes/{note_id}/pin/{pin_id}")
def unpin_note(note_id: int, pin_id: int):
    try:
        with Session(engine) as session:
            note = session.get(Note, note_id)
            if not note or note.user_id != USER_ID:
                raise HTTPException(404, "Note not found")

            pin = session.get(NotePin, pin_id)
            if not pin or pin.note_id != note_id:
                raise HTTPException(404, "Pin not found")

            session.delete(pin)
            session.commit()
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to unpin note: {str(e)}")


# Get notes for specific entities
@app.get("/trays/{tray_id}/notes", response_model=list[NoteOut])
def get_tray_notes(tray_id: int):
    with Session(engine) as session:
        tray = get_tray_or_404(session, tray_id)

        pins = session.exec(
            select(NotePin).where(
                NotePin.entity_type == "tray",
                NotePin.entity_id == tray_id
            )
        ).all()

        notes = []
        for pin in pins:
            note = session.get(Note, pin.note_id)
            if note and note.user_id == USER_ID:
                notes.append(note_to_out(session, note))

        return notes


@app.get("/cases/{case_id}/notes", response_model=list[NoteOut])
def get_case_notes(case_id: int):
    with Session(engine) as session:
        case = session.get(Case, case_id)
        if not case or case.user_id != USER_ID:
            raise HTTPException(404, "Case not found")

        pins = session.exec(
            select(NotePin).where(
                NotePin.entity_type == "case",
                NotePin.entity_id == case_id
            )
        ).all()

        notes = []
        for pin in pins:
            note = session.get(Note, pin.note_id)
            if note and note.user_id == USER_ID:
                notes.append(note_to_out(session, note))

        return notes


@app.get("/doctors/{doctor_id}/notes", response_model=list[NoteOut])
def get_doctor_notes(doctor_id: int):
    with Session(engine) as session:
        doctor = session.get(Doctor, doctor_id)
        if not doctor or doctor.user_id != USER_ID:
            raise HTTPException(404, "Doctor not found")

        pins = session.exec(
            select(NotePin).where(
                NotePin.entity_type == "doctor",
                NotePin.entity_id == doctor_id
            )
        ).all()

        notes = []
        for pin in pins:
            note = session.get(Note, pin.note_id)
            if note and note.user_id == USER_ID:
                notes.append(note_to_out(session, note))

        return notes
    
@app.get("/standalone-items/{item_id}/notes", response_model=list[NoteOut])
def get_standalone_notes(item_id: int):
    with Session(engine) as session:
        item = session.get(StandaloneItem, item_id)
        if not item or item.user_id != USER_ID:
            raise HTTPException(404, "Standalone item not found")

        pins = session.exec(
            select(NotePin).where(
                NotePin.entity_type == "standalone",
                NotePin.entity_id == item_id
            )
        ).all()

        notes = []
        for pin in pins:
            note = session.get(Note, pin.note_id)
            if note and note.user_id == USER_ID:
                notes.append(note_to_out(session, note))

        return notes
    
@app.get("/standalone-items/{item_id}/notes", response_model=list[NoteOut])
def get_standalone_notes(item_id: int):
    with Session(engine) as session:
        item = session.get(StandaloneItem, item_id)
        if not item or item.user_id != USER_ID:
            raise HTTPException(404, "Standalone item not found")

        pins = session.exec(
            select(NotePin).where(
                NotePin.entity_type == "standalone",
                NotePin.entity_id == item_id
            )
        ).all()

        notes = []
        for pin in pins:
            note = session.get(Note, pin.note_id)
            if note and note.user_id == USER_ID:
                notes.append(note_to_out(session, note))

        return notes

# =========================
# PHOTO ENDPOINTS
# =========================

@app.post("/photos", response_model=PhotoOut)
def upload_photo(payload: UploadPhotoIn):
    try:
        with Session(engine) as session:
            # Verify entity exists
            if payload.entity_type == "tray":
                entity = session.get(Tray, payload.entity_id)
                if not entity:
                    raise HTTPException(404, "Tray not found")
            elif payload.entity_type == "case":
                entity = session.get(Case, payload.entity_id)
                if not entity or entity.user_id != USER_ID:
                    raise HTTPException(404, "Case not found")
            elif payload.entity_type == "standalone":
                entity = session.get(StandaloneItem, payload.entity_id)
                if not entity or entity.user_id != USER_ID:
                    raise HTTPException(404, "Standalone item not found")
            
            photo = Photo(
                user_id=USER_ID,
                entity_type=payload.entity_type,
                entity_id=payload.entity_id,
                filename=payload.filename,
                image_data=payload.image_data,
                caption=payload.caption
            )
            session.add(photo)
            session.commit()
            session.refresh(photo)
            
            return PhotoOut(
                id=photo.id,
                user_id=photo.user_id,
                entity_type=photo.entity_type,
                entity_id=photo.entity_id,
                filename=photo.filename,
                image_data=photo.image_data,
                caption=photo.caption,
                created_at=photo.created_at
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to upload photo: {str(e)}")


@app.get("/photos/{entity_type}/{entity_id}", response_model=list[PhotoOut])
def get_photos(entity_type: str, entity_id: int):
    if entity_type not in ["tray", "case", "standalone"]:
        raise HTTPException(400, "Invalid entity type")
    
    with Session(engine) as session:
        photos = session.exec(
            select(Photo).where(
                Photo.entity_type == entity_type,
                Photo.entity_id == entity_id,
                Photo.user_id == USER_ID
            ).order_by(Photo.created_at.desc())
        ).all()
        
        return [PhotoOut(
            id=p.id,
            user_id=p.user_id,
            entity_type=p.entity_type,
            entity_id=p.entity_id,
            filename=p.filename,
            image_data=p.image_data,
            caption=p.caption,
            created_at=p.created_at
        ) for p in photos]


@app.delete("/photos/{photo_id}")
def delete_photo(photo_id: int):
    try:
        with Session(engine) as session:
            photo = session.get(Photo, photo_id)
            if not photo or photo.user_id != USER_ID:
                raise HTTPException(404, "Photo not found")
            
            session.delete(photo)
            session.commit()
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to delete photo: {str(e)}")
    
# =========================
# METRICS ENDPOINTS
# =========================

class ItemMetric(BaseModel):
    item_name: str
    sku: Optional[str]
    source_type: str  # 'tray' or 'standalone'
    source_name: str
    is_critical: bool
    times_used: int
    total_qty_used: int
    last_used: Optional[datetime]
    avg_qty_per_use: float

@app.get("/metrics/item-utilization")
def get_item_utilization(days: Optional[int] = Query(None, ge=1)):
    """Get item utilization metrics across all trays and standalone items"""
    with Session(engine) as session:
        # Calculate cutoff date if days specified
        cutoff_date = None
        if days:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        metrics = {}
        
        # Get all tray inventory check events
        query = select(Event).where(Event.type == "inventory_check")
        if cutoff_date:
            query = query.where(Event.timestamp >= cutoff_date)
        events = session.exec(query).all()
        
        # Process tray items
        for event in events:
            if not event.payload_data:
                continue
                
            try:
                payload = json.loads(event.payload_data)
                items_flagged = payload.get('items_flagged', [])
                
                for item_id in items_flagged:
                    tray_item = session.get(TrayItem, item_id)
                    if not tray_item:
                        continue
                    
                    tray = session.get(Tray, tray_item.tray_id)
                    if not tray:
                        continue
                    
                    # Create unique key for item
                    key = f"tray_{tray_item.tray_id}_{tray_item.sku}"
                    
                    if key not in metrics:
                        metrics[key] = {
                            'item_name': tray_item.name,
                            'sku': tray_item.sku,
                            'source_type': 'tray',
                            'source_name': tray.name,
                            'is_critical': tray_item.is_critical,
                            'times_used': 0,
                            'total_qty_used': 0,
                            'last_used': None,
                            'uses': []
                        }
                    
                    metrics[key]['times_used'] += 1
                    
                    # Try to get quantity from restock task items
                    task = session.exec(
                        select(RestockTask).where(
                            RestockTask.tray_id == tray.id,
                            RestockTask.created_at >= event.timestamp - timedelta(minutes=5),
                            RestockTask.created_at <= event.timestamp + timedelta(minutes=5)
                        )
                    ).first()
                    
                    qty_used = 0
                    if task:
                        task_item = session.exec(
                            select(RestockTaskItem).where(
                                RestockTaskItem.task_id == task.id,
                                RestockTaskItem.item_id == item_id
                            )
                        ).first()
                        if task_item and task_item.qty_missing:
                            qty_used = task_item.qty_missing
                    
                    metrics[key]['total_qty_used'] += qty_used
                    metrics[key]['uses'].append({'timestamp': event.timestamp, 'qty': qty_used})
                    
                    if not metrics[key]['last_used'] or event.timestamp > metrics[key]['last_used']:
                        metrics[key]['last_used'] = event.timestamp
                        
            except (json.JSONDecodeError, KeyError):
                continue
        
        # Get standalone item inventory check events
        standalone_query = select(Event).where(Event.type == "inventory_check_standalone")
        if cutoff_date:
            standalone_query = standalone_query.where(Event.timestamp >= cutoff_date)
        standalone_events = session.exec(standalone_query).all()
        
        # Process standalone item events
        for event in standalone_events:
            if not event.payload_data:
                continue
            
            try:
                payload = json.loads(event.payload_data)
                item_id = payload.get('standalone_item_id')
                qty_used = payload.get('qty_used', 0)
                
                if not item_id:
                    continue
                
                item = session.get(StandaloneItem, item_id)
                if not item:
                    continue
                
                key = f"standalone_{item_id}"
                
                if key not in metrics:
                    metrics[key] = {
                        'item_name': item.name,
                        'sku': item.sku,
                        'source_type': 'standalone',
                        'source_name': item.name,
                        'is_critical': item.is_critical,
                        'times_used': 0,
                        'total_qty_used': 0,
                        'last_used': None,
                        'uses': []
                    }
                
                metrics[key]['times_used'] += 1
                metrics[key]['total_qty_used'] += qty_used
                metrics[key]['uses'].append({'timestamp': event.timestamp, 'qty': qty_used})
                
                if not metrics[key]['last_used'] or event.timestamp > metrics[key]['last_used']:
                    metrics[key]['last_used'] = event.timestamp
                    
            except (json.JSONDecodeError, KeyError):
                continue
        
        # Add all tray items that haven't been used yet
        all_trays = session.exec(select(Tray)).all()
        for tray in all_trays:
            tray_items = session.exec(select(TrayItem).where(TrayItem.tray_id == tray.id)).all()
            for tray_item in tray_items:
                key = f"tray_{tray_item.tray_id}_{tray_item.sku}"
                if key not in metrics:
                    metrics[key] = {
                        'item_name': tray_item.name,
                        'sku': tray_item.sku,
                        'source_type': 'tray',
                        'source_name': tray.name,
                        'is_critical': tray_item.is_critical,
                        'times_used': 0,
                        'total_qty_used': 0,
                        'last_used': None,
                        'uses': []
                    }
        
        # Add all standalone items that haven't been used yet
        all_standalone_items = session.exec(
            select(StandaloneItem).where(StandaloneItem.user_id == USER_ID)
        ).all()
        for item in all_standalone_items:
            key = f"standalone_{item.id}"
            if key not in metrics:
                metrics[key] = {
                    'item_name': item.name,
                    'sku': item.sku,
                    'source_type': 'standalone',
                    'source_name': item.name,
                    'is_critical': item.is_critical,
                    'times_used': 0,
                    'total_qty_used': 0,
                    'last_used': None,
                    'uses': []
                }
        
        # Convert to list and calculate averages
        result = []
        for key, data in metrics.items():
            avg_qty = data['total_qty_used'] / data['times_used'] if data['times_used'] > 0 else 0
            result.append(ItemMetric(
                item_name=data['item_name'],
                sku=data['sku'],
                source_type=data['source_type'],
                source_name=data['source_name'],
                is_critical=data['is_critical'],
                times_used=data['times_used'],
                total_qty_used=data['total_qty_used'],
                last_used=data['last_used'],
                avg_qty_per_use=round(avg_qty, 2)
            ))
        
        # Sort by times used (descending), then by name for items with same usage
        result.sort(key=lambda x: (-x.times_used, x.item_name.lower()))
        
        return result
    
# =========================
# STANDALONE ITEM ENDPOINTS
# =========================

@app.post("/standalone-items", response_model=StandaloneItemOut)
def create_standalone_item(payload: CreateStandaloneItemIn):
    try:
        with Session(engine) as session:
            item = StandaloneItem(
                user_id=USER_ID,
                name=f"{payload.item_type} - {payload.name}",
                item_type=payload.item_type,
                sku=payload.sku,
                qty_expected=payload.qty_expected,
                qty_on_hand=payload.qty_on_hand,
                is_critical=payload.is_critical,
                status=TrayStatus.ready,
                color=COLOR_GREEN
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return item
    except Exception as e:
        raise HTTPException(500, f"Failed to create standalone item: {str(e)}")


@app.get("/standalone-items", response_model=list[StandaloneItemOut])
def list_standalone_items():
    with Session(engine) as session:
        items = session.exec(
            select(StandaloneItem).where(StandaloneItem.user_id == USER_ID)
        ).all()
        return items


@app.get("/standalone-items/{item_id}", response_model=StandaloneItemOut)
def get_standalone_item(item_id: int):
    with Session(engine) as session:
        item = session.get(StandaloneItem, item_id)
        if not item or item.user_id != USER_ID:
            raise HTTPException(404, "Standalone item not found")
        return item
    
# =========================
# STANDALONE ITEM ENDPOINTS
# =========================

@app.post("/standalone-items", response_model=StandaloneItemOut)
def create_standalone_item(payload: CreateStandaloneItemIn):
    try:
        with Session(engine) as session:
            item = StandaloneItem(
                user_id=USER_ID,
                name=f"{payload.item_type} - {payload.name}",
                item_type=payload.item_type,
                sku=payload.sku,
                qty_expected=payload.qty_expected,
                qty_on_hand=payload.qty_on_hand,
                is_critical=payload.is_critical,
                status=TrayStatus.ready,
                color=COLOR_GREEN
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return item
    except Exception as e:
        raise HTTPException(500, f"Failed to create standalone item: {str(e)}")


@app.get("/standalone-items", response_model=list[StandaloneItemOut])
def list_standalone_items():
    with Session(engine) as session:
        items = session.exec(
            select(StandaloneItem).where(StandaloneItem.user_id == USER_ID)
        ).all()
        return items


@app.get("/standalone-items/{item_id}", response_model=StandaloneItemOut)
def get_standalone_item(item_id: int):
    with Session(engine) as session:
        item = session.get(StandaloneItem, item_id)
        if not item or item.user_id != USER_ID:
            raise HTTPException(404, "Standalone item not found")
        return item


@app.post("/standalone-items/{item_id}/dropoff")
def dropoff_standalone(item_id: int, payload: DropoffRequest):
    try:
        with Session(engine) as session:
            item = session.get(StandaloneItem, item_id)
            if not item or item.user_id != USER_ID:
                raise HTTPException(404, "Standalone item not found")
            
            item.status = TrayStatus.in_location
            item.last_seen_lat = payload.gps.lat
            item.last_seen_lng = payload.gps.lng
            item.last_seen_at = datetime.now(timezone.utc)
            item.last_location_type = payload.location_type
            item.last_location_name = payload.location_name
            
            item.color = map_color(item.priority_numeric, item.priority_partial, item.status == TrayStatus.ready)
            
            session.add(item)
            session.commit()
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to drop off standalone item: {str(e)}")


@app.post("/standalone-items/{item_id}/inventory-check")
def inventory_check_standalone(item_id: int, payload: BaseModel):
    try:
        with Session(engine) as session:
            item = session.get(StandaloneItem, item_id)
            if not item or item.user_id != USER_ID:
                raise HTTPException(404, "Standalone item not found")
            
            # Update quantity
            qty_used = payload.__dict__.get('qty_used', 0)
            if qty_used > 0:
                current_qty = item.qty_on_hand or 0
                item.qty_on_hand = max(0, current_qty - qty_used)
            
            # Create event to track usage (for metrics)
            gps_data = payload.__dict__.get('gps', {})
            evt = Event(
                tray_id=0,  # Use 0 to indicate standalone item
                user_id=USER_ID,
                type="inventory_check_standalone",
                timestamp=datetime.now(timezone.utc),
                gps_lat=gps_data.get('lat') if isinstance(gps_data, dict) else None,
                gps_lng=gps_data.get('lng') if isinstance(gps_data, dict) else None,
                payload_data=json.dumps({
                    "standalone_item_id": item_id,
                    "qty_used": qty_used
                })
            )
            session.add(evt)
            
            item.status = TrayStatus.needs_restock
            item.last_seen_lat = gps_data.get('lat') if isinstance(gps_data, dict) else None
            item.last_seen_lng = gps_data.get('lng') if isinstance(gps_data, dict) else None
            item.last_seen_at = datetime.now(timezone.utc)
            
            user_priority = payload.__dict__.get('user_priority_numeric')
            if user_priority:
                item.priority_numeric = user_priority
            
            item.color = map_color(item.priority_numeric, item.priority_partial, item.status == TrayStatus.ready)
            
            if payload.__dict__.get('location_type'):
                item.last_location_type = payload.__dict__.get('location_type')
                item.last_location_name = payload.__dict__.get('location_name')
            
            session.add(item)
            session.commit()
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to check inventory: {str(e)}")


@app.post("/standalone-items/{item_id}/restock-full")
def restock_full_standalone(item_id: int, payload: RestockFullRequest):
    try:
        with Session(engine) as session:
            item = session.get(StandaloneItem, item_id)
            if not item or item.user_id != USER_ID:
                raise HTTPException(404, "Standalone item not found")
            
            if item.qty_expected is not None:
                item.qty_on_hand = item.qty_expected
            
            item.status = TrayStatus.ready
            item.priority_numeric = None
            item.priority_partial = False
            item.color = map_color(item.priority_numeric, item.priority_partial, ready=True)
            
            if payload.location_type:
                item.last_location_type = payload.location_type
                item.last_location_name = payload.location_name
                item.last_seen_at = datetime.now(timezone.utc)
            
            session.add(item)
            session.commit()
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to restock: {str(e)}")


@app.post("/standalone-items/{item_id}/restock-partial")
def restock_partial_standalone(item_id: int, payload: BaseModel):
    try:
        with Session(engine) as session:
            item = session.get(StandaloneItem, item_id)
            if not item or item.user_id != USER_ID:
                raise HTTPException(404, "Standalone item not found")
            
            qty_restocked = payload.__dict__.get('qty_restocked', 0)
            if qty_restocked > 0:
                current_qty = item.qty_on_hand or 0
                if item.qty_expected is not None:
                    item.qty_on_hand = min(current_qty + qty_restocked, item.qty_expected)
                else:
                    item.qty_on_hand = current_qty + qty_restocked
            
            # Check if fully restocked
            if item.qty_expected and item.qty_on_hand >= item.qty_expected:
                item.status = TrayStatus.ready
                item.priority_numeric = None
                item.priority_partial = False
            else:
                item.status = TrayStatus.needs_restock
                new_priority = payload.__dict__.get('new_priority')
                if new_priority == 'partial':
                    item.priority_partial = True
                    item.priority_numeric = None
                else:
                    item.priority_numeric = int(new_priority)
                    item.priority_partial = False
            
            item.color = map_color(item.priority_numeric, item.priority_partial, item.status == TrayStatus.ready)
            
            if payload.__dict__.get('location_type'):
                item.last_location_type = payload.__dict__.get('location_type')
                item.last_location_name = payload.__dict__.get('location_name')
                item.last_seen_at = datetime.now(timezone.utc)
            
            session.add(item)
            session.commit()
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to partial restock: {str(e)}")