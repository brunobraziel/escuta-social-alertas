"""Leitura limitada de HTML público, sem scripts, login ou contorno de bloqueios."""
import logging
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from datetime import datetime, timezone

from core.alerta import clean
from pesquisas_eleitorais.parser import matches_poll


class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip = 0; self.parts = []; self.meta = {}; self.links = []; self.anchor = None; self.in_article = False; self.article_parts = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article":
            self.in_article = True
        if tag in ('script','style','noscript'):
            self.skip += 1
        if tag == 'meta':
            self.meta[attrs.get('property',attrs.get('name',''))] = attrs.get('content','')
        if tag == 'a':
            self.anchor = [attrs.get('href',''), []]
        if tag in ('p','li','h1','h2','h3','br') and not self.skip:
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag == "article":
            self.in_article = False
        if tag in ('script','style','noscript'):
            self.skip = max(0,self.skip-1)
        if tag == 'a' and self.anchor:
            self.links.append((self.anchor[0],clean(' '.join(self.anchor[1])))); self.anchor=None
    def handle_data(self, value):
        if not self.skip:
            self.parts.append(value)
            if self.in_article:
                self.article_parts.append(value)
            if self.anchor:
                self.anchor[1].append(value)


def read_page(url, hosts):
    if urlparse(url).scheme != 'https' or urlparse(url).hostname not in hosts:
        raise ValueError('Host de notícia não autorizado')
    with urlopen(Request(url,headers={'User-Agent':'EscutaSocialAlertas/0.1 (news reader)'}),timeout=25) as response:
        if urlparse(response.geturl()).hostname not in hosts:
            raise ValueError('Redirecionamento para host não autorizado')
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:
        raise ValueError('HTML excede limite')
    page=Page(); page.feed(raw.decode('utf-8',errors='replace')); return page


def article_from_page(page, url):
    date = page.meta.get('article:published_time','')
    published=datetime.fromisoformat(date.replace('Z','+00:00'))
    if published.tzinfo is None or not -300 <= (datetime.now(timezone.utc)-published).total_seconds() <= 168*3600:
        return None
    return {'title':page.meta.get('og:title',''), 'url':url, 'published':published.isoformat(), 'description':clean(' '.join(page.article_parts or page.parts))[:120000]}


def enrich(article, hosts):
    return article_from_page(read_page(article['url'],hosts),article['url'])


def discover(url, hosts, limit=6):
    page=read_page(url,hosts)
    urls=[]
    for href,title in page.links:
        target=urljoin(url,href).split('#')[0]
        if urlparse(target).scheme != 'https' or urlparse(target).hostname not in hosts or target in urls:
            continue
        if matches_poll(title, ''):
            urls.append(target)
    result=[]
    for target in urls[:limit]:
        try:
            article=article_from_page(read_page(target,hosts),target)
        except Exception as error:
            logging.warning('Matéria ignorada após falha de leitura (%s)',type(error).__name__)
            continue
        if article and matches_poll(article['title'],article['description']):
            result.append(article)
    return result
