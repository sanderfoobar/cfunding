from enum import Enum


class WithdrawalStatus(Enum):
    pending = 0
    completed = 1
    error = 2


class ProposalCategory(Enum):
    wallets = 0
    marketing = 1
    core = 2
    misc = 3
    design = 4

    @staticmethod
    def lookup():
        return {
            0: "Wallets",
            1: "Marketing",
            2: "Core",
            3: "Miscellaneous",
            4: "Design"
        }

    @staticmethod
    def to_string(cat: 'ProposalCategory.value'):
        if isinstance(cat, ProposalCategory):
            cat = cat.value
        return ProposalCategory.lookup()[cat]

    @staticmethod
    def keys():
        return list(ProposalCategory.lookup().keys())


class ProposalStatus(Enum):
    disabled = 0
    idea = 1
    funding_required = 2
    wip = 3
    completed = 4

    @staticmethod
    def lookup():
        return {
            0: "Disabled",
            1: "idea",
            2: "Funding Required",
            3: "WIP",
            4: "Completed"
        }

    @staticmethod
    def to_string(cat: 'ProposalStatus.value'):
        if isinstance(cat, ProposalStatus):
            cat = cat.value
        return ProposalStatus.lookup()[cat]

    @staticmethod
    def keys():
        return list(ProposalStatus.lookup().keys())


class UserRole(Enum):
    anonymous = 0
    user = 1
    moderator = 2
    admin = 3
