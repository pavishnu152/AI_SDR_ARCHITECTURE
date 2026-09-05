import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def _password_must_fit_bcrypt(cls, v: str) -> str:
        # bcrypt hashes at most 72 BYTES of input, not 72 characters. A
        # plain Field(max_length=72) only counts characters, so a password
        # under 72 characters can still exceed 72 bytes once it contains any
        # multi-byte UTF-8 character (accents, symbols, emoji, etc.) — that
        # slips past a character-count check but still crashes bcrypt deep
        # inside hash_password() with an unhandled ValueError. Checking the
        # real UTF-8 byte length here is what actually matches bcrypt's
        # limit, and turns that crash into a clean 422 instead.
        if len(v.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes when UTF-8 encoded")
        return v


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
