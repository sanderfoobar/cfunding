from funding.utils.markdown import MARKDOWN_PROPOSAL_DEFAULT
from funding.models.enums import ProposalCategory, ProposalStatus

COINS_LOOKUP = {
    "wownero": {
        "ticker": "WOW",
        "address_length": [97, 108],
        "coingecko_id": "wownero"
    },
    "firo": {
        "ticker": "FIRO",
        "address_length": 34,
        "coingecko_id": "zcoin"
    },
    "monero": {
        "ticker": "XMR",
        "address_length": 95,
        "coingecko_id": "monero"
    },
    "bitcoin": {
        "ticker": "BTC",
        "address_length": [25, 35],
        "coingecko_id": "bitcoin"
    }
}

GLOBALS = {
    "ProposalCategory": ProposalCategory,
    "ProposalStatus": ProposalStatus,
    "COINS_LOOKUP": COINS_LOOKUP,
    "MARKDOWN_PROPOSAL_DEFAULT": MARKDOWN_PROPOSAL_DEFAULT
}
