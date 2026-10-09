from pydantic import BaseModel

from app.modules.voice_experiences.application.contracts import Command


def command_from_model(model: BaseModel) -> Command:
    return Command(model.model_dump(mode="json"))
