from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.identity.api.deps import get_current_auth_context
from app.modules.identity.public import AuthContext


def get_current_internal_db(
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> Session:
    if not context.user.is_internal:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Internal platform access required")
    return db
