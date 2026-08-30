from fastapi import APIRouter, Request, Response

from ..services.security_service import resolve_request_identity


router = APIRouter(prefix="/api/identity", tags=["identity"])


@router.post("")
def establish_identity(request: Request, response: Response):
    resolve_request_identity(request, response)
    return {"ok": True}
