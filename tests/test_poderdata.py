import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.alerta import identifier
from pesquisas_eleitorais.parser import matches_poll, parse_poll, parse_notice
from pesquisas_eleitorais.run import run
from pesquisas_eleitorais.web import Page


def news():
    return {'title':'Pesquisa PoderData/Aya: resultados no 2º turno para presidente',
            'url':'https://www.poder360.com.br/poderdata/exemplo/', 'published':'2026-10-16T12:25:55+00:00',
            'description':'O presidente Luiz Inácio Lula da Silva (PT) e o senador Flávio Bolsonaro (PL) estão empatados, com 50% dos votos válidos cada um. Pesquisa nacional realizada de 13 a 15 de outubro, com 3.000 entrevistas. A margem de erro é de 1,8 ponto percentual e o intervalo de confiança é de 95%. Registro BR-04258/2026.'}


class ExpandedPollTests(unittest.TestCase):
    def test_poderdata_valid_votes_and_metadata(self):
        poll=parse_poll(news())
        self.assertIsNotNone(poll)
        self.assertEqual([r['percent'] for r in poll['results']], [50,50])
        self.assertEqual(poll['base'],'votos_validos')
        self.assertEqual(poll['registration'],'BR-04258/2026')

    def test_institute_outside_catalog_not_blocked(self):
        item=news();item['title']='Pesquisa Instituto Exemplo Novo: presidente no 2º turno'
        self.assertTrue(matches_poll(item['title'],item['description']))
        self.assertEqual(parse_poll(item)['institute'],'Instituto Exemplo Novo')

    def test_not_infer_tie_or_mix_historical_values(self):
        item=news();item['description']=item['description'].replace('50%','49%')
        self.assertIsNone(parse_poll(item))
        self.assertTrue(parse_notice(item)['notice'])
        self.assertEqual(parse_notice(item)['results'],[])

    def test_notice_requires_registration_and_presidential_scope(self):
        item=news();item['description']=item['description'].replace('BR-04258/2026','')
        self.assertIsNone(parse_notice(item))
        self.assertFalse(matches_poll('PoderData: rejeição chega a 40%',''))

    def test_excludes_script_percentages_and_preserves_article_text(self):
        p=Page();p.feed('<script>Errado 99%</script><article><p>Certo 50%</p></article>')
        self.assertNotIn('Errado',' '.join(p.parts))
        self.assertIn('Certo 50%',' '.join(p.article_parts))

    def test_older_unsent_not_hidden_by_newer_sent(self):
        new=news();old=news();old['published']='2026-10-15T12:25:55+00:00';old['description']=old['description'].replace('BR-04258/2026','BR-11111/2026')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json';path.write_text(json.dumps({'sent':[identifier('pesquisa:BR-04258/2026:presidente:BR:2:votos_validos')],'preserve':'yes'}))
            with patch.dict('os.environ',{'DISCORD_WEBHOOK_URL':'hook'}),patch('pesquisas_eleitorais.run.fetch_feed',return_value=[]),patch('pesquisas_eleitorais.run.discover',return_value=[new,old]),patch('pesquisas_eleitorais.run.send_discord',return_value={'id':'1'}) as send:
                run(['--state',str(path)])
                send.assert_called_once()
                self.assertIn('BR-11111/2026',send.call_args.args[1]['message'])
                self.assertEqual(json.loads(path.read_text())['preserve'],'yes')

    def test_regional_presidential_poll_not_labelled_national(self):
        item=news();item['title']='PoderData: Lula e Flávio no 2º turno no Amazonas'
        self.assertIsNone(parse_poll(item))
        self.assertIsNone(parse_notice(item))

    def test_current_valid_percentages_from_title_map_to_explicit_names(self):
        item=news();item['title']='PoderData: Flávio tem 50,5% dos votos válidos no 2º turno; Lula, 49,5%'
        item['description']=item['description'].replace('estão empatados, com 50% dos votos válidos cada um','disputam o segundo turno')
        poll=parse_poll(item)
        self.assertIsNotNone(poll)
        self.assertEqual([r['percent'] for r in poll['results']],[50.5,49.5])


class SecondRoundLeadTests(unittest.TestCase):
    def test_round_in_lead_missing_from_title_still_notifies_without_inferred_numbers(self):
        item = news()
        item['title'] = 'Flávio reage e vai a 52% contra 48% de Lula, diz PoderData/Aya'
        item['description'] = 'A seis dias do segundo turno, pesquisa nacional para presidente. ' + item['description'].replace('BR-04258/2026', 'BR-02586/2026')
        notice = parse_notice(item)
        self.assertIsNotNone(notice)
        self.assertTrue(notice['notice'])
        self.assertEqual(notice['registration'], 'BR-02586/2026')
        self.assertEqual(notice['results'], [])

    def test_first_round_title_does_not_borrow_second_round_from_body(self):
        item = news()
        item['title'] = 'PoderData: pesquisa para presidente no 1º turno'
        item['description'] = 'Cenário histórico do segundo turno. ' + item['description']
        self.assertIsNone(parse_poll(item))
        self.assertIsNone(parse_notice(item))

    def test_mentions_after_lead_do_not_change_scope(self):
        item = news()
        item['title'] = 'PoderData: pesquisa para presidente'
        item['description'] = 'Texto sem definição de turno. ' * 100 + ' segundo turno ' + item['description']
        self.assertIsNone(parse_notice(item))
