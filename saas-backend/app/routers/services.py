from fastapi import APIRouter

from app.catalog import SERVICES
from app.schemas import ServiceOut


router = APIRouter(prefix="/v1/services", tags=["services"])


@router.get("", response_model=list[ServiceOut])
def list_services() -> list[ServiceOut]:
    return [ServiceOut.model_validate(service) for service in SERVICES]

