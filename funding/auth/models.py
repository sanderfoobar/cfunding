from typing import Optional

from dataclasses import dataclass
from pydantic import BaseModel, EmailStr


class UserRegisterForm(BaseModel):
    username: str
    email: EmailStr
    password: str
    captcha: str
