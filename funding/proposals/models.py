from typing import Optional
from datetime import datetime

from pydantic import (
    BaseModel,
    NegativeFloat,
    NegativeInt,
    PositiveFloat,
    PositiveInt,
    NonNegativeFloat,
    NonNegativeInt,
    NonPositiveFloat,
    NonPositiveInt,
    conbytes,
    condecimal,
    confloat,
    conint,
    conlist,
    conset,
    constr,
    Field,
    UUID4
)

from funding.models.enums import ProposalStatus, ProposalCategory


class ProposalFundsTransfer(BaseModel):
    captcha: str
    amount: constr(min_length=1)
    destination: constr(min_length=4, max_length=256)


class CommentPostReply(BaseModel):
    markdown: constr(min_length=1, max_length=4000)
    comment_uuid: UUID4

    class Config:
        use_enum_values = True


class CommentPost(BaseModel):
    markdown: constr(min_length=1, max_length=4000)
    proposal_uuid: UUID4

    class Config:
        use_enum_values = True


class ProposalUpsert(BaseModel):
    title: constr(min_length=8, max_length=64)
    slug: Optional[str]
    markdown: constr(min_length=20)
    funds_target: confloat(gt=0)
    category: ProposalCategory
    status: Optional[ProposalStatus]
    discourse_topic_id: Optional[int]
    addr_receiving: constr(min_length=8, max_length=128)

    class Config:
        use_enum_values = False
