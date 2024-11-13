from fastapi import HTTPException, status    


def get_user_exception():
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return credentials_exception


def get_unknown_entity_exception():
    entity_exception = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Entity not found"
    )
    return entity_exception