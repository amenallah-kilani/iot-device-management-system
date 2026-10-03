import secrets
from sqlalchemy import*
from sqlalchemy.orm import*
from datetime import*
from pydantic import*
from datetime import timedelta
from fastapi import FastAPI, Depends, HTTPException

Base = declarative_base()

#______tables__________
class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String)
    api_key = Column(String , unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    #relationship
    status = relationship("DeviceStatus" , back_populates="device", uselist=False)
    logs = relationship("Log", back_populates="device")

# DeviceStatus table
class DeviceStatus(Base):
    __tablename__ = "device_status"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"))
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, default=datetime.utcnow)

    device = relationship("Device", back_populates="status")

# Logs table
class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"))
    action = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    device = relationship("Device", back_populates="logs")
    


#_______database setup________
from sqlalchemy import create_engine
engine = create_engine("sqlite:///./iot.db", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)

#________Database session setup_________
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


#________schema____________
class DeviceCreate(BaseModel):
    name: str
    type: str

class DeviceRead(BaseModel):
    id: int
    name: str
    type: str
    api_key: str
    created_at: datetime

    class Config:
        from_attributes = True
# FastAPI app
app = FastAPI()

@app.post("/devices", response_model=DeviceRead)
def create_device(device: DeviceCreate, db: Session = Depends(get_db)):
    api_key = secrets.token_hex(16)  # generate random API key
    new_device = Device(
        name=device.name,
        type=device.type,
        api_key=api_key
    )
    db.add(new_device)
    db.commit()
    db.refresh(new_device)
    return new_device

@app.post("/devices/{device_id}/heartbeat")
def heartbeat(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Update or create status
    if device.status:
        device.status.is_online = True
        device.status.last_seen = datetime.utcnow()
    else:
        status = DeviceStatus(
            device_id=device.id,
            is_online=True,
            last_seen=datetime.utcnow()
        )
        db.add(status)

    # Add log entry
    log = Log(device_id=device.id, action="heartbeat")
    db.add(log)
    db.commit()
    return {"message": f"Heartbeat received for device {device.name}"}
@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total_devices = db.query(Device).count()
    online_devices = db.query(DeviceStatus).filter(DeviceStatus.is_online == True).count()
    offline_devices = total_devices - online_devices
    error_rate = (offline_devices / total_devices * 100) if total_devices > 0 else 0

    return {
        "total_devices": total_devices,
        "online_devices": online_devices,
        "offline_devices": offline_devices,
        "error_rate_percent": round(error_rate, 2)
    }

