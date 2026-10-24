import unittest
from tendencias_rss.run import parse, fingerprint, render

class TrendsRssTest(unittest.TestCase):
    def feed(self, items):
        return ('<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>'+items+'</channel></rss>').encode()

    def item(self, title, date, news='', traffic='5000+'):
        return f'<item><title>{title}</title><pubDate>{date}</pubDate><ht:approx_traffic>{traffic}</ht:approx_traffic><ht:news_item><ht:news_item_title>{news}</ht:news_item_title></ht:news_item></item>'

    def test_filter_politics_from_headline_and_order(self):
        raw=self.feed(self.item('futebol','Fri, 23 Oct 2026 18:00:00 -0300')+self.item('whisky macallan','Fri, 23 Oct 2026 19:00:00 -0300','Mensagens sobre Lula e Vorcaro')+self.item('debate na globo','Fri, 23 Oct 2026 20:00:00 -0300')+self.item('DEBATE NA GLOBO','Fri, 23 Oct 2026 20:00:00 -0300'))
        topics=parse(raw)
        self.assertEqual([t['title'] for t in topics],['debate na globo','whisky macallan'])
        self.assertIn('Política',render(topics)['whatsapp_message'])

    def test_dedup_ignores_timestamp_but_tracks_list(self):
        a=[{'title':'Lula','traffic':'5000+','published':'a'}]
        b=[dict(a[0],published='b')]
        self.assertEqual(fingerprint(a),fingerprint(b))
        self.assertNotEqual(fingerprint(a),fingerprint([dict(a[0],traffic='10000+')]))

    def test_invalid_date_and_unrelated_are_not_published(self):
        self.assertEqual(parse(self.feed(self.item('Lula','invalid')+self.item('jogo','Fri, 23 Oct 2026 20:00:00 -0300'))),[])
