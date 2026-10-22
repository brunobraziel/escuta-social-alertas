import hashlib
import hmac
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from PIL import Image

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/'infra/whatsapp'))
import cards
import worker
from tendencias_bq.estados import render as states
from tendencias_bq.em_alta_brasil import STATE_NAMES
from tendencias_bq.monitoramento_temas import render as related
from datetime import datetime, timezone


def state_text(term='Assunto variável'):
    rows=[dict(uf=uf,termo=f'{term} {n}',indice_vs_ancora=10-n,eh_ancora=False,grupo='g',periodo='now 1-d') for uf in STATE_NAMES for n in range(5)]
    return states(rows,datetime.now(timezone.utc))['whatsapp_message']


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=str(Path(self.temp.name)/'db.sqlite')
        self.db=worker.connect(self.path)
        self.env=patch.dict(os.environ,{'ALLOWED_SOURCES':'brunobraziel/escuta-social-alertas'})
        self.env.start()
    def tearDown(self):
        self.env.stop();self.db.close();self.temp.cleanup()
    def event(self,text,presentation='states'):
        return dict(version=1,event_id='b'*64,source='brunobraziel/escuta-social-alertas',text=text,presentation=presentation)
    def sent_image(self):
        full=state_text(); worker.accept(self.db,self.event(full))
        http=Mock();http.get.return_value.json.return_value={'status':'WORKING'}
        http.post.return_value.json.return_value={'key':{'id':'IMAGE123','remoteJid':'123@g.us','fromMe':True}}
        self.assertTrue(worker.send_one(self.db,http,'http://waha','123@g.us','key'))
        return full,http
    def reaction(self,**changes):
        p=dict(fromMe=False,participant='5511999999999@c.us',reaction={'text':'♿','messageId':'true_123@g.us_IMAGE123'})
        p['from']='123@g.us';p.update(changes)
        return dict(event='message.reaction',session='default',payload=p)
    def test_image_transport_archives_exact_text_and_no_group_rankings(self):
        full,http=self.sent_image();args=http.post.call_args
        self.assertTrue(args.args[0].endswith('/api/sendImage'))
        body=args.kwargs['json'];self.assertNotIn('Assunto variável',body['caption'])
        self.assertIn('♿',body['caption']);self.assertNotIn('text',body)
        self.assertEqual(self.db.execute('SELECT text FROM accessible_reports').fetchone()[0],full)
        self.assertEqual(len(cards.parse_states(full)[1]),27)
    def test_image_gets_visible_accessibility_reaction_once(self):
        full,http=self.sent_image()
        http.put.assert_called_once()
        body=http.put.call_args.kwargs['json']
        self.assertEqual(body,{'session':'default','messageId':'true_123@g.us_IMAGE123','reaction':'♿'})
        self.assertEqual(self.db.execute('SELECT status FROM image_reactions').fetchone()[0],'sent')
        self.assertFalse(worker.seed_reaction(self.db,http,'http://waha','key'))
        self.assertFalse(worker.accept_reaction(self.db,self.reaction(fromMe=True),'123@g.us'))
        self.assertIn('Reaja a esta imagem com ♿ para receber o texto completo no privado.',http.post.call_args.kwargs['json']['caption'])
    def test_reaction_retry_never_resends_confirmed_image(self):
        worker.accept(self.db,self.event(state_text()))
        http=Mock();http.get.return_value.json.return_value={'status':'WORKING'}
        http.post.return_value.json.return_value={'id':'true_123@g.us_IMAGE123'}
        http.put.side_effect=[TimeoutError(),Mock()]
        self.assertTrue(worker.send_one(self.db,http,'http://waha','123@g.us','key'))
        self.assertEqual(self.db.execute('SELECT status FROM deliveries').fetchone()[0],'sent')
        self.assertTrue(worker.seed_reaction(self.db,http,'http://waha','key'))
        self.assertFalse(worker.send_one(self.db,http,'http://waha','123@g.us','key'))
        self.assertEqual(http.post.call_count,1)
        self.assertEqual(http.put.call_args_list[0].kwargs['json'],http.put.call_args_list[1].kwargs['json'])
    def test_reaction_replies_once_privately_with_same_snapshot(self):
        full,http=self.sent_image()
        self.assertTrue(worker.accept_reaction(self.db,self.reaction(),'123@g.us'))
        self.assertTrue(worker.accept_reaction(self.db,self.reaction(),'123@g.us'))
        replies=self.db.execute("SELECT payload FROM deliveries WHERE status='pending'").fetchall()
        self.assertEqual(len(replies),1);reply=json.loads(replies[0][0])
        self.assertEqual(reply['text'],full);self.assertNotIn('presentation',reply)
        http.post.return_value.json.return_value={'id':'PRIVATE123'}
        while worker.send_one(self.db,http,'http://waha','123@g.us','key'):pass
        private=[x.kwargs['json'] for x in http.post.call_args_list if x.args[0].endswith('/api/sendText')]
        self.assertTrue(private)
        self.assertTrue(all(x['chatId']=='5511999999999@c.us' for x in private))
        self.assertEqual('\n\n'.join(x['text'] for x in private),full)
    def test_wrong_group_self_unknown_message_and_other_emoji_ignored(self):
        self.sent_image()
        bad=[{'from':'other@g.us'},{'fromMe':True},{'participant':'bad'},
             {'reaction':{'text':'👍','messageId':'IMAGE123'}},
             {'reaction':{'text':'♿','messageId':'unknown'}}]
        for params in bad:self.assertFalse(worker.accept_reaction(self.db,self.reaction(**params),'123@g.us'))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM deliveries WHERE status='pending'").fetchone()[0],0)
    def test_media_timeout_keeps_uncertain_and_never_replays(self):
        worker.accept(self.db,self.event(state_text()))
        http=Mock();http.get.return_value.json.return_value={'status':'WORKING'};http.post.side_effect=TimeoutError()
        worker.send_one(self.db,http,'http://waha','123@g.us','key')
        worker.send_one(self.db,http,'http://waha','123@g.us','key')
        self.assertEqual(http.post.call_count,1)
        self.assertEqual(self.db.execute('SELECT status FROM deliveries').fetchone()[0],'uncertain')
    def test_dynamic_rankings_change_image_and_keep_135_terms(self):
        first=state_text('Saúde');second=state_text('Educação')
        a,_=cards.render_images('states',first);b,_=cards.render_images('states',second)
        self.assertNotEqual(a,b)
        self.assertEqual(sum(len(c['topics']) for c in cards.parse_states(second)[1]),135)
        self.assertGreater(Image.open(io.BytesIO(a[0])).width,3000)
    def test_related_variants_and_long_topics_preserved_and_paginated(self):
        text='*Consultas relacionadas*\n\n*Dados atualizados:* hoje'
        for n in range(23):
            text+=f'\n\n*Candidatos* — Brasil\nBusca-base: base {n}\n1. *consulta {n} '+('longa '*20)+'*\n   Agrupadas: variante A · variante B\n2. *Outra consulta*'
        _,parsed=cards.parse_related(text)
        self.assertEqual(len(parsed),23);self.assertTrue(all('variante B' in c['topics'][0][2] for c in parsed))
        images,_=cards.render_images('related',text)
        self.assertGreater(len(images),1)
        self.assertTrue(all(Image.open(io.BytesIO(i)).height<8000 for i in images))
    def test_webhook_hmac_rejects_forged_request(self):
        group=Path(self.temp.name)/'group';group.write_text('123@g.us')
        # Bind an ephemeral local port in tests without changing production binding.
        original=worker.ThreadingHTTPServer
        with patch('socket.getfqdn',return_value='localhost'), patch.object(worker,'ThreadingHTTPServer',side_effect=lambda addr,handler:original(('127.0.0.1',0),handler)):
            server=worker.start_reaction_server(self.path,group,'webhook-key')
        try:
            endpoint=f'http://127.0.0.1:{server.server_port}/reactions';body=json.dumps(self.reaction()).encode()
            with self.assertRaises(HTTPError) as bad:urlopen(Request(endpoint,data=body),timeout=3)
            self.assertEqual(bad.exception.code,403)
            signature=hmac.new(b'webhook-key',body,hashlib.sha512).hexdigest()
            with urlopen(Request(endpoint,data=body,headers={'X-Webhook-Hmac':signature}),timeout=3) as r:self.assertEqual(r.status,200)
        finally:server.shutdown();server.server_close()
    def test_publisher_cannot_supply_private_destination(self):
        with self.assertRaises(ValueError):worker.accept(self.db,dict(self.event('test'),destination='5511999999999@c.us'))
