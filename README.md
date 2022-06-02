# cFunding

A simple cryptocurrency funding system made with:

- Python
- [Quart web-framework](https://pgjones.gitlab.io/quart/)
- [pewee ORM](https://docs.peewee-orm.com/en/latest/peewee/quickstart.html)
- Postgres
- Redis

## Installation

TL;DR:

```bash
apt install -y python3-virtualenv libjpeg-dev libpng-dev python3 redis-server postgresql postgresql-contrib postgresql-server-dev-*

virtualenv -p /usr/bin/python3 venv
source venv/bin/activate

pip install -r requirements.txt
cp settings.py_example settings.py

# change the settings, then execute `run.py`
python3 run.py
```

Alternatively use `asgi.py` for usage via [hypercorn](https://pypi.org/project/hypercorn/) or 
[uvicorn](https://pypi.org/project/uvicorn/).

### Settings

Some options in `settings.py` need changing:

1. Set: `DB_*` - point to a Postgres database
2. Optional: `REDIS_URI` *if* your Redis instance has a non-default configuration 
3. Optional: `X_FORWARDED` to `True` *if* proxied by a webserver (`X-Forwarded-For` expected)
4. Set `APP_SECRET`.
5. Set `DOMAIN` to `mydomain.com`
6. Optional: `DISCOURSE_*` related options to connect to Discourse
7. Set `COIN_*`, see also below 'Coin configuration'

### Discourse (optional)

Discourse, the forum software, has an API key we can generate:

```text
[YourSite]/admin/api/keys
```

[Some handy Discourse options to change](https://meta.discourse.org/t/global-rate-limits-and-throttling-in-discourse/78612):

- Increase `DISCOURSE_MAX_ADMIN_API_REQS_PER_MINUTE`
- Increase `DISCOURSE_MAX_REQS_PER_IP_PER_10_SECONDS`

This will include the comments from Discourse on the proposal page and turn on automatic Discourse topic creation 
when a proposal is posted.

### Coin configuration (Firo)

Download and extract [the most recent release](https://github.com/firoorg/firo/releases/) to get `firod`. 

Run this somewhere (via a [systemd unit file](https://github.com/firoorg/firo/wiki/Configuring-masternode-with-systemd), or just a screen/tmux session, etc.):

```text
./firod -rpcbind=127.0.0.1 \ 
        -rpcallowip=127.0.0.1 \ 
        -rpcport=18888 \
        -rpcuser=admin \
        -rpcpassword=admin
```

And set `settings.py` options:

- Set `COIN_NAME` to `'firo'`
- Set `COIN_RPC_PORT` to `18888`
- Set `COIN_RPC_AUTH` to `'admin,admin'`

## History

The development of cfunding is a joint effort by [Firo](https://firo.org/) and [Wownero](https://wownero.org/)

## License

MIT