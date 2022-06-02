import bcrypt
import json
import asyncio
from typing import List, Optional
from uuid import uuid4
import hashlib
from copy import deepcopy
from datetime import datetime

import peewee as pw
from peewee import JOIN
from aiocryptocurrency.coins import TransactionSet, Transaction
import playhouse.postgres_ext as pwpg
from quart import url_for, session, current_app as app, g
from funding.utils import safu
from slugify import slugify

import settings
from funding.factory import crypto_provider, discourse, coin
from funding.proposals.models import ProposalUpsert
from funding.models.enums import UserRole, ProposalStatus, WithdrawalStatus, ProposalCategory
from funding.models.utils import EnumField
from funding.utils.discourse import DiscourseComment
from funding.utils.markdown import generate_html


class User(pw.Model):
    uuid = pw.UUIDField(primary_key=True, default=uuid4)
    created = pw.DateTimeField(default=datetime.now)
    modified = pw.DateTimeField(default=datetime.now)
    enabled = pw.BooleanField(default=True)

    username = pw.CharField(unique=True, index=True, max_length=16)
    password = pw.CharField(max_length=128)
    oip = pw.CharField(max_length=128, null=True)  # OpenID Identity Provider name
    mail: str = pw.TextField(unique=True)
    role: UserRole = EnumField(choices=UserRole, default=UserRole.user)
    withdrawal_address: str = pw.TextField(index=True, null=True)

    proposals: List['Proposal'] = None

    class Meta:
        from funding.factory import database
        database = database

    @property
    def is_admin(self):
        if isinstance(self.role, int):
            return self.role == UserRole.admin.value
        return self.role.value == UserRole.admin.value

    @property
    def is_anon(self):
        if isinstance(self.role, int):
            return self.role == UserRole.anonymous.value
        return self.role.value == UserRole.anonymous.value

    @property
    def is_moderator(self):
        if isinstance(self.role, int):
            return self.role >= UserRole.moderator.value
        return self.role.value >= UserRole.moderator.value

    @staticmethod
    def by_uuid(uuid):
        try:
            return User.select()\
                .join(Proposal, pw.JOIN.LEFT_OUTER) \
                .where(User.uuid == uuid).get()
        except Exception as ex:
            pass

    @staticmethod
    def validate(username: str, password: str) -> Optional['User']:
        try:
            user = User.select().filter(User.username == username).get()
            if bcrypt.checkpw(password.encode(), user.password.encode()):
                return user
        except:
            pass

    async def to_json(self):
        return {
            "uuid": self.uuid,
            "username": self.username,
            "mail": self.mail,
            "role": self.role.value,
            "mail_md5": hashlib.md5(self.mail.encode()).hexdigest()
        }


class Proposal(pw.Model):
    uuid = pw.UUIDField(primary_key=True, default=uuid4)
    created = pw.DateTimeField(default=datetime.now)
    modified = pw.DateTimeField(default=datetime.now)

    user = pw.ForeignKeyField(User, backref='proposals')
    title: str = pw.CharField(max_length=255, index=True)
    addr_receiving: str = pw.CharField(max_length=255)
    markdown: str = pw.TextField(index=True)
    html: str = pw.TextField()
    slug: str = pw.TextField(index=True, unique=True)

    discourse_topic_id = pw.IntegerField(null=True)

    views = pw.IntegerField(default=0)

    category: ProposalCategory = EnumField(choices=ProposalCategory, default=ProposalCategory.misc)
    status: ProposalStatus = EnumField(choices=ProposalStatus, default=ProposalStatus.idea)

    # proposal target
    funds_target: float = pw.FloatField(null=False)
    funds_progress: float = pw.FloatField(null=False, default=0)

    crypto_address_donation: str = pw.TextField(null=True)
    crypto_address_payment_id: str = pw.TextField(null=True)

    withdrawals: List['Withdrawal'] = None
    events: List['Event'] = None

    def __init__(self, *args, **kwargs):
        super(Proposal, self).__init__(*args, **kwargs)
        self._is_new = False
        self._events: List['Event'] = []

    @property
    async def comments(self) -> List[DiscourseComment]:
        cache = app.session_interface
        res = await cache.get(self.comments_cache_key)
        if res:
            return [DiscourseComment.parse_raw(c) for c in json.loads(res)]
        return []

    def can_edit(self, user: User):
        if user.role.value == UserRole.admin.value or \
                user.role.value == UserRole.moderator.value:
            return True
        if user.username == self.user.username:
            return True
        return False

    @property
    def funds_target_human(self):
        target = str(self.funds_target)
        if target.endswith(".0"):
            target = target[:-2]
        return target

    @property
    def comments_cache_key(self):
        return f"topic_comments_{self.discourse_topic_id}"

    @property
    def discourse_topic_link(self):
        if not self.discourse_topic_id:
            return ''
        return f"https://{settings.DISCOURSE_DOMAIN}/t/{self.discourse_topic_id}"

    @property
    def donations_enabled(self) -> bool:
        if self.crypto_address_donation == "" or self.crypto_address_donation is None:
            return False
        if self.status != ProposalStatus.funding_required:
            return False
        return True

    @property
    async def transactions(self) -> TransactionSet:
        incoming = await self._fetch_incoming_txs(
            address=self.crypto_address_donation,
            payment_id=self.crypto_address_payment_id
        )
        outgoing = TransactionSet()
        try:
            for w in Withdrawal.select().filter(
                    Withdrawal.proposal == self,
                    Withdrawal.status == WithdrawalStatus.completed):
                outgoing.add(Transaction(
                    amount=w.amount,
                    txid=w.txid,
                    direction='out',
                    date=w.created
                ))
        except Exception as ex:
            app.logger.error(ex)
        return incoming + outgoing

    @property
    async def spent_remaining(self) -> float:
        ts = await self.transactions
        sum_in = ts.sum('in')
        sum_out = ts.sum('out')
        if sum_in == 0:
            return 0.0
        res = sum_in - sum_out
        if res <= 0:
            return 0.0
        return round(res, 10)

    @property
    async def spent(self) -> TransactionSet:
        ts = await self.transactions
        a = ts.filter('out')
        return a

    @property
    async def spent_pct(self) -> float:
        ts = await self.transactions
        incoming = ts.filter('in')
        outgoing = ts.filter('out')
        incoming_sum = incoming.sum('in')
        outgoing_sum = outgoing.sum('out')
        if outgoing_sum <= 0 or incoming_sum <= 0:
            return 0.0

        res = 100 * float(outgoing_sum) / float(incoming_sum)
        res = round(res, 2)
        return res

    @property
    async def raised_remaining(self):
        ts = await self.transactions
        ts = ts.filter('in')
        return self.funds_target - ts.sum()

    @property
    async def raised(self) -> TransactionSet:
        txs = await self.transactions
        return txs.filter('in')

    @property
    async def raised_pct(self):
        ts = await self.transactions
        ts = ts.filter('in')

        part = ts.sum()
        if part == 0.0:
            return 0

        pct = 100 * float(part) / float(self.funds_target)
        pct = round(pct, 2)
        # if pct > 100:
        #     pct = 100

        if pct > self.funds_progress:
            self.funds_progress = pct
            self.save()

        return pct

    @staticmethod
    async def post_topic(proposal: 'Proposal', href_to_proposal: str):
        """Post topic @ Discourse"""
        discourse_title = settings.DISCOURSE_TOPIC_TITLE.format(
            title=proposal.title,
            author=proposal.user.username)
        discourse_body = settings.DISCOURSE_TOPIC_BODY.format(
            author=proposal.user.username,
            ptype=ProposalCategory.to_string(proposal.category),
            link=href_to_proposal,
            title=proposal.title)
        try:
            return await discourse.new_topic(
                title=discourse_title,
                body=discourse_body,
                category=settings.DISCOURSE_TOPIC_CATEGORY)
        except Exception as ex:
            app.logger.error(f"Discourse new_topic error: {ex}")

    def set_discourse_topic_id(self, topic_id: int, user: User):
        if not isinstance(topic_id, int) or topic_id == self.discourse_topic_id:
            return
        if not user.is_moderator:
            raise Exception("insufficient permissions to change 'discourse_topic_id'")
        self.discourse_topic_id = topic_id
        self.modified = datetime.now()

    async def set_status(self, status: ProposalStatus, user: User = None):
        if not isinstance(status, ProposalStatus) or status is self.status:
            return
        if user and not user.is_moderator:
            raise Exception("insufficient permissions to change 'status'.")

        if not self._is_new:
            status_from = ProposalStatus.to_string(self.status)
            status_to = ProposalStatus.to_string(status)

            self.status = status
            self.modified = datetime.now()

            message = f"Status changed from '{status_from}' to '{status_to}'"
            self._events.append(Event(message=message, proposal=self, user=user))

            try:
                if isinstance(self.discourse_topic_id, int):
                    await discourse.new_post(self.discourse_topic_id, message)
            except:
                pass

    async def set_category(self, cat: ProposalCategory, user: User = None):
        if not isinstance(cat, ProposalCategory) or cat is self.category:
            return
        self.modified = datetime.now()

        if self._is_new:
            self.category = cat
        else:
            cat_from = ProposalCategory.to_string(self.category)
            cat_to = ProposalCategory.to_string(cat)
            self.category = cat

            message = f"Category changed from '{cat_from}' to '{cat_to}'"
            self._events.append(Event(
                message=message,
                proposal=self,
                user=user))

            try:
                if isinstance(self.discourse_topic_id, int):
                    await discourse.new_post(self.discourse_topic_id, message)
            except:
                pass

    def set_markdown(self, markdown: str, user: User):
        if not isinstance(markdown, str) or \
                self.markdown == markdown:
            return

        self.markdown = markdown
        self.html = generate_html(markdown)
        self.modified = datetime.now()

        if not self._is_new:
            self._events.append(Event(
                message="Proposal markdown updated",
                proposals=self,
                user=user))

    async def set_funds_target(self, funds_target: float, user: User = None):
        if self.funds_target == funds_target:
            return

        if self.funds_target is None:
            self.funds_target = funds_target
            return

        float_from = round(self.funds_target, 4)
        float_to = round(funds_target, 4)

        ticker = coin['ticker']
        message = f"Funding target changed from " \
                  f"'{float_from} {ticker}' to " \
                  f"'{float_to} {ticker}'"

        self.funds_target = funds_target
        self._events.append(Event(
            message=message,
            proposal=self,
            user=user))

        if isinstance(self.discourse_topic_id, int):
            try:
                await discourse.new_post(self.discourse_topic_id, body=message)
            except:
                pass

    def set_addr_receiving(self, addr_receiving: str, user: User = None):
        if not addr_receiving or addr_receiving == self.addr_receiving:
            return

        self.addr_receiving = addr_receiving
        if self._is_new:
            return
        elif self.addr_receiving != addr_receiving:
            msg = "user-defined receiving address changed"
            self._events.append(Event(
                message=msg,
                proposal=self,
                user=user))

    def generate_slug(self, title: str):
        return f"{slugify(title)}-{self.user.username}"

    async def generate_deposit_address(self, user: User = None):
        from funding.factory import crypto_provider
        if self.crypto_address_donation:
            return
        if self.status.value <= ProposalStatus.idea.value:
            return

        try:
            blob = await crypto_provider.create_address()
            self.crypto_address_donation = blob['address']
            if 'payment_id' in blob:
                self.crypto_address_payment_id = blob['payment_id']

            self._events.append(Event(message=f"Donation address generated", proposal=self, user=user))
        except Exception as ex:
            raise Exception(f"Failed to generate address {ex}")

    async def generate_discourse_topic(self, topic_id: Optional[int], user=None):
        if isinstance(topic_id, int) and topic_id != self.discourse_topic_id:
            self.discourse_topic_id = topic_id
            self._events.append(Event(message="Discourse topic id changed", proposal=self, user=user))
            return
        if not settings.DISCOURSE_ENABLED or isinstance(self.discourse_topic_id, int):
            return

        href = url_for('bp_proposals.view', slug=self.slug, _external=True)
        res = await Proposal.post_topic(self, href)
        if isinstance(res, int):
            self.discourse_topic_id = res
            self._events.append(Event(
                message="Discourse topic posted",
                proposal=self,
                user=user))
        else:
            app.logger.error(f"discourse topic post error: {json.dumps(res)}")
            self._events.append(Event(
                message="Discourse topic post error; check application logs",
                proposal=self,
                user=user))

    @classmethod
    async def upsert(cls, data: ProposalUpsert):
        # updating or inserting a proposal
        user: User = g.user
        if not user:
            raise Exception("whoami?")

        if data.slug:
            proposal = await Proposal.by_slug(data.slug)
        else:
            proposal = Proposal()
            proposal.user = user
            proposal.status = ProposalStatus.idea
            proposal._is_new = True
            proposal._events.append(Event(message="Proposal created", user=user, proposal=proposal))

        if user.is_anon or (
                not user.is_moderator and proposal.user.username != user.username):
            raise Exception("insufficient permissions.")

        proposal.title = data.title
        if proposal._is_new:
            proposal.slug = proposal.generate_slug(data.title)

        proposal.set_addr_receiving(data.addr_receiving, user)
        await proposal.set_category(data.category, user)
        await proposal.set_status(data.status, user)
        await proposal.set_funds_target(data.funds_target, user)
        await proposal.generate_deposit_address(user)
        await proposal.generate_discourse_topic(topic_id=data.discourse_topic_id, user=user)
        proposal.set_markdown(data.markdown, user)

        proposal.modified = datetime.now()
        proposal.save(force_insert=proposal._is_new)

        for event in proposal._events:
            event.proposal = proposal
            event.save(force_insert=True)
        return proposal

    @staticmethod
    async def by_slug(slug: str):
        try:
            p = Proposal.select().join(Event, JOIN.LEFT_OUTER).where(Proposal.slug == slug).get()
            await p.check_funding_status()
            return p
        except Exception as ex:
            pass

    @safu
    async def check_funding_status(self) -> bool:
        """Auto-move proposals to 'wip' if fully funded"""
        if self._is_new:
            return False
        if self.status != ProposalStatus.funding_required:
            return False

        res = await self.raised_pct
        if res >= 100:
            await self.set_status(ProposalStatus.wip)
            self.save()
            return True
        return False

    @staticmethod
    async def _fetch_incoming_txs(address, payment_id=None, cache_expiry=60) -> Optional[TransactionSet]:
        txset = TransactionSet()
        if not address:
            return txset

        cache = app.session_interface
        key = f"txs_{address}"

        # try to get it from the `g` object
        if hasattr(g, key):
            val = getattr(g, key)
            if isinstance(val, str):
                results = json.loads(val)
                return TransactionSet.from_json(results)
            return val

        # maybe it is in cache?
        data = await cache.get(key)
        if data:
            results = json.loads(data)
            return TransactionSet.from_json(results)

        try:
            # contact RPC; list txs
            txs = await crypto_provider.list_txs(
                address=address,
                payment_id=payment_id,
                minimum_confirmations=3)
            serialized = txs.serialize()
        except Exception as ex:
            app.logger.error(f"Could not list_txs(); {ex}")
            return txset

        await cache.set(key, serialized, cache_expiry)
        setattr(g, key, serialized)
        return txs

    class Meta:
        from funding.factory import database
        database = database


class Event(pw.Model):
    uuid = pw.UUIDField(primary_key=True, default=uuid4)
    created = pw.DateTimeField(default=datetime.now)
    modified = pw.DateTimeField(default=datetime.now)

    message = pw.TextField()
    data = pw.TextField(null=True)
    proposal: Proposal = pw.ForeignKeyField(Proposal, backref='events', null=False)
    user: User = pw.ForeignKeyField(User, null=True)

    class Meta:
        from funding.factory import database
        database = database


class Withdrawal(pw.Model):
    uuid = pw.UUIDField(primary_key=True, default=uuid4)
    created = pw.DateTimeField(default=datetime.now)
    modified = pw.DateTimeField(default=datetime.now)

    txid = pw.TextField(null=False)
    amount = pw.FloatField(null=False)
    status = EnumField(choices=WithdrawalStatus, default=WithdrawalStatus.pending)
    proposal = pw.ForeignKeyField(Proposal, backref="withdrawals")

    class Meta:
        from funding.factory import database
        database = database


class System(pw.Model):
    uuid = pw.UUIDField(primary_key=True, default=uuid4)
    created = pw.DateTimeField(default=datetime.now)
    modified = pw.DateTimeField(default=datetime.now)

    name = pw.CharField(max_length=16)
    value = pwpg.BinaryJSONField()

    class Meta:
        from funding.factory import database
        database = database
