from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/infer")
def infer():
    return {"score": 0.0}
