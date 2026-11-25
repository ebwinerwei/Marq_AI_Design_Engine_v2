import sqlite3
import unittest
from unittest.mock import patch

from engine import jobs
import server


class PilotOperations(unittest.TestCase):
    def test_expiry_recovery_and_stale_worker(self):
        c=sqlite3.connect(':memory:')
        self.addCleanup(c.close)
        c.execute('create table task(id text primary key,status text,msg text)')
        c.execute("insert into task values('j','queued','')")
        jobs.register(c,'j')
        with patch('engine.jobs.time.time',return_value=1000):
            self.assertEqual(jobs.acquire(c,'j','first'),'owned')
            c.execute("update task set status='running',msg='first'")
            self.assertTrue(jobs.renew(c,'j','first'))
            c.commit()
        with patch('engine.jobs.time.time',return_value=1061):
            self.assertFalse(jobs.renew(c,'j','first'));c.commit()
            self.assertEqual(jobs.recover(c),[]);c.commit()
            self.assertEqual(c.execute('select status from task').fetchone()[0],'queued')
        with patch('engine.jobs.time.time',return_value=1065):
            self.assertEqual(jobs.recover(c),['j']);c.commit()
            self.assertEqual(jobs.acquire(c,'j','second'),'owned')
            c.execute("update task set status='running',msg='second'")
            self.assertFalse(jobs.renew(c,'j','first'))
            self.assertTrue(jobs.renew(c,'j','second'))

    def test_channel_contract_binding_and_revocation(self):
        record=dict(account='QA',model='mock',endpoint='https://example.invalid/intent',contract='offline fixture',
                    region='test',retention='test',sampleTest='synthetic QA',expires='2099-01-01')
        cfg=dict(approved=True,textModel='mock',textUrl=record['endpoint'],verifiedChannels={'text':record})
        channel=server.pilot_channels(cfg)['text']
        spec=dict(externalConsent=True,channelGrants={'text':channel['id']})
        self.assertEqual(server.authorized_channel(cfg,'text',spec),channel)
        with self.assertRaises(ValueError):server.authorized_channel(cfg,'image',spec)
        for key,value in [('expires','2000-01-01'),('endpoint','https://example.invalid/other'),('account','other')]:
            changed=dict(cfg,verifiedChannels={'text':dict(record,**{key:value})})
            with self.assertRaises(ValueError):server.authorized_channel(changed,'text',spec)
