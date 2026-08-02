import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.services.auth import get_current_user
from app.services.credits import get_balance

logger = logging.getLogger("jroots")

router = APIRouter(prefix="/api/credits", tags=["credits"])


@router.get("")
async def get_credits(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_balance(db, current_user.id)
