import copy
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import main
import utils
import food_scanner
import sales_scanner
import refresh_food_sales
from deal_score import final_hotel_score, promo_score
from offer_metadata import enrich_offer, is_expired
from scan_health import ScanResult, EmptyHotelScan, record_scan
FIXTURE = json.loads((Path(__file__).parent / 'fixtures/review.json').read_text())

class ScoringTests(unittest.TestCase):
    def test_72_equals_47_plus_25(self):
        item=copy.deepcopy(FIXTURE['hotel_peer'])
        self.assertEqual(final_hotel_score(item),72)
        d=item['score_breakdown']
        self.assertEqual(d['base_total'],47)
        self.assertEqual(d['bonus'],25)
        self.assertEqual(d['total'],72)
        self.assertEqual(sum(p['points'] for p in d['components'])+sum(p['points'] for p in d['adjustments']),72)
    def test_peer_and_current_caps(self):
        item=copy.deepcopy(FIXTURE['hotel_peer'])
        item.update(historical_median=1000,breakfast=True,lounge=True,bathtub=True,flexible_cancellation=True)
        self.assertEqual(final_hotel_score(item),84)
        d=item['score_breakdown'];self.assertLess(d['cap_adjustment'],0)
        self.assertAlmostEqual(sum(p['points'] for p in d['components'])+sum(p['points'] for p in d['adjustments']),84)
        item['score_basis']='current_only';self.assertEqual(final_hotel_score(item),69)
    def test_promos_components_and_qualifiers(self):
        for name in ['up_to','one_for_one']:
            item=copy.deepcopy(FIXTURE[name]);n=promo_score(item)
            self.assertAlmostEqual(sum(c['points'] for c in item['score_breakdown']['components']),n)
        self.assertEqual(enrich_offer(copy.deepcopy(FIXTURE['up_to']))['discount_qualifier'],'up_to')
        self.assertEqual(enrich_offer(copy.deepcopy(FIXTURE['one_for_one']))['discount_qualifier'],'equivalent')
    def test_ideas_preserve_hotel_context(self):
        hotel=copy.deepcopy(FIXTURE['hotel_peer']);hotel['deal_score']=final_hotel_score(hotel)
        idea=main.build_ideas([hotel],70)[0]
        for key in ['check_in','check_out','source','price_type','is_evaluation','observed_at','current_price','total_price','score_breakdown']:
            self.assertEqual(idea[key],hotel[key])
        self.assertEqual(idea['hotel_name'],hotel['name']);self.assertIn('transport',idea['cost_scope'])
    def test_food_different_offers_survive(self):
        a={'name':'Venue @ One','restaurant_name':'Venue @ One','category':'food','meal_period':'lunch','url':'https://example.com'}
        b={**a,'meal_period':'dinner'};c={**a,'restaurant_name':'Venue @ Two'};d={**a,'access_requirement':'Card required'}
        self.assertEqual(len(food_scanner.dedupe_food([a,a,b,c,d])),4)
    def test_expiry_inclusive_and_unknown(self):
        self.assertFalse(is_expired({'valid_until':'2026-11-13'},date(2026,11,13)))
        self.assertTrue(is_expired({'valid_until':'2026-11-12'},date(2026,11,13)))
        self.assertFalse(is_expired({'valid_until':'unknown'},date(2026,11,13)))

class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patch=patch.object(utils,'ROOT',self.root);self.patch.start()
        for category in ['hotels','food','sales','deals']:
            utils.write_json(f'data/{category}.json',{'updated_at':'2026-11-01T07:00:00+08:00','items':[copy.deepcopy(FIXTURE['hotel_peer'])] if category in ['hotels','deals'] else [{'id':'old','category':'food' if category=='food' else 'sale'}]})
        utils.write_json('data/history.json',{'observations':[{'id':'keep'}]})
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def test_hotel_failure_preserves_all_published_files(self):
        for error,state in [(RuntimeError('sensitive payload must not be published'),'failed_retained'),(EmptyHotelScan(),'empty_retained')]:
            before={p.name:p.read_bytes() for p in (self.root/'data').glob('*.json') if p.name!='scan-status.json'}
            with patch.object(main,'scan_hotels',side_effect=error),patch.object(main,'scan_food') as food:
                with self.assertRaises(RuntimeError):main.main()
                food.assert_not_called()
            for name,content in before.items():self.assertEqual((self.root/'data'/name).read_bytes(),content)
            status=utils.read_json('data/scan-status.json')['sources']['hotels'];self.assertEqual(status['state'],state)
            self.assertEqual(status['last_success'],'2026-11-01T07:00:00+08:00')
            self.assertNotIn('sensitive',(self.root/'data/scan-status.json').read_text())
    def test_empty_food_success_differs_from_failed_retained(self):
        with patch.object(food_scanner,'fetch_html',return_value='<html><body>No qualifying offers</body></html>'):
            result=food_scanner.scan_food();self.assertEqual(result.state,'empty');self.assertFalse(result)
        with patch.object(food_scanner,'fetch_html',side_effect=OSError('offline')),patch.object(food_scanner,'load_previous_live_food',return_value=[{'id':'old','observed_at':'2020-01-01'}]):
            result=food_scanner.scan_food();self.assertEqual(result.state,'failed_retained');self.assertEqual(result[0]['observed_at'],'2020-01-01')
    def test_empty_sales_does_not_relabel_old_as_new(self):
        with patch.object(sales_scanner,'fetch_html',return_value='<html><body>No offers</body></html>'),patch.object(sales_scanner,'load_previous_live_sales') as previous:
            result=sales_scanner.scan_sales();self.assertEqual(result.state,'empty');self.assertEqual(result,[]);previous.assert_not_called()
    def test_failed_food_and_sales_times_preserved(self):
        failure=[{'name':'Fixture source','url':'https://example.com','status':'failed','last_attempt':'2026-11-13T08:00:00+08:00'}]
        with patch.object(refresh_food_sales,'scan_food',return_value=ScanResult([{'id':'old','category':'food'}],failure,True)),patch.object(refresh_food_sales,'scan_sales',return_value=ScanResult([],failure,True)):
            history=(self.root/'data/history.json').read_bytes();hotels=(self.root/'data/hotels.json').read_bytes()
            refresh_food_sales.main()
            self.assertEqual(utils.read_json('data/food.json')['updated_at'],'2026-11-01T07:00:00+08:00')
            self.assertEqual(utils.read_json('data/deals.json')['source_updated_at']['sales'],'2026-11-01T07:00:00+08:00')
            self.assertEqual((self.root/'data/hotels.json').read_bytes(),hotels);self.assertEqual((self.root/'data/history.json').read_bytes(),history)
    def test_partial_scan_records_source_failure(self):
        result=ScanResult([{'id':'new'}],[{'name':'a','url':'https://a','status':'success','last_attempt':'2026-11-13T08:00:00+08:00'},{'name':'b','url':'https://b','status':'failed','last_attempt':'2026-11-13T08:00:00+08:00'}])
        s=record_scan('food',result);self.assertEqual(s['state'],'partial');self.assertIsNone(s['sources'][1]['last_success']);self.assertEqual(s['last_success'],'2026-11-01T07:00:00+08:00')

if __name__=='__main__':unittest.main()
