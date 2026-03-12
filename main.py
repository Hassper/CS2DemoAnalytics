from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from cs2_demo_analytics.config import UPLOAD_DIR
from cs2_demo_analytics.database import Base, engine, get_db
from cs2_demo_analytics.models import Match
from cs2_demo_analytics.schemas import AnalyticsResponse, MatchSummary, UploadResponse
from cs2_demo_analytics.service import fetch_analytics, ingest_demo

app = FastAPI(title="CS2 Demo Analytics")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

Base.metadata.create_all(bind=engine)


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/upload", response_model=UploadResponse)
async def upload_demo(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.endswith(".dem"):
        raise HTTPException(status_code=400, detail="Only .dem files are allowed.")

    target = UPLOAD_DIR / f"{uuid4()}_{file.filename}"
    data = await file.read()
    target.write_bytes(data)

    try:
        match_id = ingest_demo(db, target, file.filename)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse demo: {exc}") from exc

    return UploadResponse(match_id=match_id, message="Demo uploaded and analyzed successfully")


@app.get("/api/matches", response_model=list[MatchSummary])
def list_matches(db: Session = Depends(get_db)):
    matches = db.query(Match).order_by(Match.uploaded_at.desc()).all()
    return [
        MatchSummary(
            id=m.id,
            demo_filename=m.demo_filename,
            map_name=m.map_name,
            uploaded_at=m.uploaded_at.isoformat(),
            total_rounds=m.total_rounds,
        )
        for m in matches
    ]


@app.get("/api/matches/{match_id}", response_model=AnalyticsResponse)
def get_match_analytics(match_id: int, db: Session = Depends(get_db)):
    try:
        return fetch_analytics(db, match_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Match analytics not found: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
