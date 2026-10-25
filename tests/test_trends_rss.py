import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from tendencias_rss.run import parse, group, render, run, KEY

NOW=datetime(2026,10,24,22,tzinfo=timezone.utc)
def topic(title,value=5000):
    return dict(title=title,traffic=f'{value}+',value=value,published=NOW.isoformat())

class TrendsRssTest(unittest.TestCase):
    def test_group_exact_variants_but_not_different_intentions(self):
        topics=[topic('flavio e vorcaro foto'),topic('foto vorcaro e flavio'),topic('flavio vorcaro investigação')]
        groups=group(topics)
        self.assertEqual([len(g) for g in groups],[2,1])
        text='\n'.join(p['message'] for p in render(topics,now=NOW))
        for t in topics:self.assertIn(t['title'],text)
        self.assertIn('sem base anterior',text)

    def test_filter_rejects_lottery_context_and_stale(self):
        raw=b'''<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
<item><title>dia de sorte</title><pubDate>Sat, 24 Oct 2026 18:00:00 -0300</pubDate><ht:news_item><ht:news_item_title>Eleicao altera sorteio</ht:news_item_title></ht:news_item></item>
<item><title>lula</title><pubDate>Sat, 24 Oct 2026 18:00:00 -0300</pubDate><ht:approx_traffic>5000+</ht:approx_traffic></item>
<item><title>bolsonaro</title><pubDate>Sat, 10 Oct 2026 18:00:00 -0300</pubDate></item></channel></rss>'''
        self.assertEqual([t['title'] for t in parse(raw,NOW)],['lula'])

    def test_comparison_ranks_and_estimates_separate(self):
        a,b=topic('lula'),topic('bolsonaro')
        pages=render([b,a],{'at':NOW.isoformat(),'topics':[a,b]},NOW)
        text='\n'.join(p['message'] for p in pages)
        self.assertIn('subiu 1',text)
        self.assertIn('antes: 5000+',text)
        self.assertIn('não são somadas',text)

    def test_failed_send_does_not_dedup_and_dry_run_preserves_state(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';p.write_text(json.dumps({'sent':['keep'],'unknown':42}))
            original=p.read_text()
            with patch('tendencias_rss.run.fetch',return_value=[topic('lula')]):
                run(['--dry-run','--state',str(p)])
                self.assertEqual(p.read_text(),original)
                with patch.dict('os.environ',{'DISCORD_WEBHOOK_URL':'configured','WHATSAPP_TOPIC':'configured'}),patch('tendencias_rss.run.send_discord',side_effect=RuntimeError('failed')):
                    with self.assertRaises(RuntimeError):run(['--state',str(p)])
                self.assertEqual(p.read_text(),original)
                with patch.dict('os.environ',{'DISCORD_WEBHOOK_URL':'configured','WHATSAPP_TOPIC':'configured'}),patch('tendencias_rss.run.send_discord') as send:
                    run(['--state',str(p)]);run(['--state',str(p)])
                    self.assertEqual(send.call_count,1)
                state=json.loads(p.read_text());self.assertEqual(state['unknown'],42);self.assertEqual(state['sent'],['keep']);self.assertIn(KEY,state)

    def test_ten_groups_all_terms_and_page_limits(self):
        topics=[topic(f'lula assunto {i}') for i in range(12)]
        pages=render(topics,now=NOW)
        self.assertEqual(len(group(topics)),10)
        self.assertTrue(all(len(p['message'])<4000 for p in pages))

class CompletePoliticsSourceTest(unittest.TestCase):
    def test_official_category_groups_keep_every_variant(self):
        from tendencias_rss.run import parse_trending
        rows=[]
        for i in range(12):
            rows.append([f'assunto político {i}',None,'BR',[int(NOW.timestamp())],None,None,100000-i,None,200,[f'consulta {i} variante {j}' for j in range(120)],[14]])
        rows.append(['futebol',None,'BR',[int(NOW.timestamp())],None,None,999999,None,200,['jogo'],[17]])
        raw="AF_initDataCallback({key: 'ds:0', hash: '2', data:"+json.dumps([None,rows])+", sideChannel: {}});"
        topics=parse_trending(raw,NOW)
        self.assertEqual(len(topics),12)
        pages=render(topics,now=NOW)
        text='\n'.join(p['message'] for p in pages)
        self.assertIn('Top 10',text)
        for t in topics[:10]:
            for term in t['terms']:self.assertIn(f'“{term}”',text)
        self.assertNotIn('consulta 10 variante',text)
        self.assertTrue(all(len(p['message'])<4000 for p in pages))
        self.assertIn('Estimativa do grupo',text)
        self.assertIn('continuação',text)

    def test_missing_complete_source_fails_without_rss_fallback(self):
        from tendencias_rss.run import parse_trending
        with self.assertRaises(ValueError):parse_trending('<html>unavailable</html>',NOW)
