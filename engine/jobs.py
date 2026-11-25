"""Leases for opt-in, locally generated artifacts. The task row remains the durable queue."""
import time

LEASE_SECONDS = 60
MAX_ATTEMPTS = 3


def installed(c):
    return bool(c.execute("select 1 from sqlite_master where type='table' and name='artifact_lease'").fetchone())


def register(c, key):
    c.execute("""create table if not exists artifact_lease(
        id text primary key references task(id), token text, until real default 0,
        attempts integer default 0, sha256 text)""")
    c.execute("insert or ignore into artifact_lease(id) values(?)", (key,))


def acquire(c, key, token):
    if not installed(c):
        return 'legacy'
    row = c.execute('select attempts,until from artifact_lease where id=?', (key,)).fetchone()
    if not row:
        return 'legacy'
    if row[0] >= MAX_ATTEMPTS or row[1] > time.time():
        return 'wait'
    c.execute('update artifact_lease set token=?, until=?,attempts=attempts+1 where id=?',
              (token, time.time()+LEASE_SECONDS, key))
    return 'owned'


def renew(c, key, token):
    now = time.time()
    return c.execute("""update artifact_lease set until=? where id=? and token=? and until>?
        and exists(select 1 from task where id=? and status='running' and msg=?)""",
                     (now+LEASE_SECONDS, key, token, now, key, token)).rowcount


def recover(c, now=None):
    if not installed(c):
        return []
    now = time.time() if now is None else now
    c.execute('begin immediate')
    for key, token, attempts in c.execute("""select t.id,l.token,l.attempts from task t
            join artifact_lease l on t.id=l.id where t.status='running' and l.until<=? and t.msg=l.token""",
            (now,)).fetchall():
        retry = attempts < MAX_ATTEMPTS
        c.execute('update task set status=?,msg=? where id=? and msg=?',
                  ('queued' if retry else 'failed', '' if retry else '再試行上限。履歴を確認してください', key, token))
        c.execute('update artifact_lease set token=null,until=? where id=?',
                  (now+2**attempts if retry else 0, key))
    return [r[0] for r in c.execute("""select t.id from task t join artifact_lease l on t.id=l.id
              where t.status='queued' and l.until<=? and l.attempts<? order by t.rowid limit 16""",
              (now, MAX_ATTEMPTS))]
