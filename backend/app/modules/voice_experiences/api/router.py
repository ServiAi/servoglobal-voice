from fastapi import APIRouter

from app.modules.voice_experiences.api.context_router import router as context_router
from app.modules.voice_experiences.api.experience_router import router as experience_router
from app.modules.voice_experiences.api.public_router import router as public_router

router = APIRouter()
router.include_router(experience_router)
router.include_router(context_router)
router.include_router(public_router)
