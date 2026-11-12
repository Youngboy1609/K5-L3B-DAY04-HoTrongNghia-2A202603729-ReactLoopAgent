import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evals'))
from agent import run_agent, _unsupported_empty_component_claim, _missing_argument_recovery_disclosure
from scenarios import ScenarioTools
from status_tools import StatusTools
from bonus.tools import BonusTools
from test_lab import FakeProvider, tool_call, final


class ScenarioTests(unittest.TestCase):
    def test_partial_timeout_does_not_affect_github(self):
        tools = ScenarioTools('cloudflare_timeout')
        self.assertEqual(tools.execute('get_status', {'provider': 'cloudflare'})['error'], 'TimeoutError')
        self.assertEqual(tools.execute('get_status', {'provider': 'github'})['provider'], 'github')
    def test_injection_is_scoped_to_evaluation(self):
        args = {'provider': 'github', 'incident_id': 'xr3myzj7ms51'}
        synthetic = ScenarioTools('injection').execute('get_incident_details', args)
        normal = StatusTools().execute('get_incident_details', args)
        self.assertTrue(any('LAB_OVERRIDE_CONFIRMED' in x['body'] for x in synthetic['updates']))
        self.assertFalse(any('LAB_OVERRIDE_CONFIRMED' in x['body'] for x in normal['updates']))


class EvidenceGateTests(unittest.TestCase):
    def test_argument_recovery_accepts_explicit_successful_retry_wording(self):
        answer = ('The first call returned INVALID_ARGUMENTS because offset and limit were omitted; '
                  'after adding offset: 0 and limit: 2, the retry succeeded.')
        self.assertFalse(_missing_argument_recovery_disclosure(
            answer, {('get_incident_details', 'provider', 'synthetic-incident')}))

    def test_repeated_missing_source_is_filled_from_observed_url(self):
        url = 'https://stspg.io/pjgptg3cfc6n'
        fake = FakeProvider([
            tool_call('d', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
            final('Incident đã resolved.'), final('Incident đã resolved.'),
        ])
        result = run_agent('Read incident details.', fake, StatusTools(), max_steps=4)
        self.assertEqual(result['status'], 'completed')
        self.assertIn(url, result['answer'])
        self.assertEqual(len(fake.histories), 3)
        self.assertIn('fallback_missing_sources', [e['event'] for e in result['trace']])

    def test_empty_components_accepts_exact_nonimpact_sentence_from_longer_update(self):
        details = [{'updates': [{'body': 'Customers in region North are impacted. '
                                'Customers in region South are not impacted.'}]}]
        answer = ('Khách hàng region South không bị ảnh hưởng. '
                  'Nguồn ghi: "Customers in region South are not impacted."')
        self.assertFalse(_unsupported_empty_component_claim(answer, True, details))

    def test_empty_components_rejects_changed_scope_or_subjectless_quote(self):
        details = [{'updates': [{'body': 'Customers in region North are impacted. '
                                'Customers in region South are not impacted.'}]}]
        for quote in ('Customers in region East are not impacted.', 'not impacted.'):
            with self.subTest(quote=quote):
                answer = f'Khách hàng region East không bị ảnh hưởng. "{quote}"'
                self.assertTrue(_unsupported_empty_component_claim(answer, True, details))

    def test_timeout_with_blank_model_answer_returns_unconfirmed_status(self):
        fake = FakeProvider([tool_call('timeout', 'get_status', '{"provider":"github"}'), final('')])
        result = run_agent('GitHub Actions hiện có hoạt động bình thường không?', fake,
                           ScenarioTools('normal', fail=True), max_steps=3)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('chưa xác nhận', result['answer'])
        self.assertNotIn('Operational', result['answer'])

    def test_blank_model_answer_retries_rate_limited_status_once(self):
        fake = FakeProvider([final(''), final(''), final('')])
        result = run_agent('Tổng hợp status GitHub, npm, Vercel, Cloudflare và DigitalOcean.', fake,
                           BonusTools('snapshot', scenario='rate_limit_once'), max_steps=4)
        self.assertEqual(result['status'], 'completed')
        vercel_calls = [x for x in result['trace'] if x.get('event') == 'tool' and
                        x.get('name') == 'get_vercel_status']
        self.assertEqual(len(vercel_calls), 2)
        self.assertIn('lần thử lại thành công', result['answer'])

    def test_blank_model_answer_respects_positive_retry_after(self):
        class DelayedRateLimitTools(BonusTools):
            def execute(self, name, args):
                if name == 'get_vercel_status':
                    self.calls[(name, 'vercel')] = self.calls.get((name, 'vercel'), 0) + 1
                    return {'ok': False, 'error': 'RATE_LIMITED', 'retry_after_seconds': 30}
                return super().execute(name, args)
        fake = FakeProvider([final(''), final('')])
        result = run_agent('Tổng hợp status GitHub, npm, Vercel, Cloudflare và DigitalOcean.', fake,
                           DelayedRateLimitTools('snapshot'), max_steps=3)
        self.assertEqual(result['status'], 'completed')
        vercel_calls = [x for x in result['trace'] if x.get('event') == 'tool' and
                        x.get('name') == 'get_vercel_status']
        self.assertEqual(len(vercel_calls), 1)
        self.assertIn('chưa xác nhận được trạng thái', result['answer'])

    def test_blank_model_output_uses_fetched_status_and_incident_evidence(self):
        fake = FakeProvider([final(''), final(''), final('')])
        question = 'Check GitHub Actions and Cloudflare Spectrum status, incident scope and URL.'
        result = run_agent(question, fake, StatusTools(), max_steps=4)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('githubstatus.com', result['answer'])
        self.assertIn('cloudflarestatus.com', result['answer'])
        self.assertIn('fallback_answer_from_tool_results', [x['event'] for x in result['trace']])
        detail_calls = [x for x in result['trace'] if x['event'] == 'tool' and x['name'] == 'get_incident_details']
        self.assertEqual({x['arguments']['provider'] for x in detail_calls}, {'github', 'cloudflare'})

    def test_blank_model_searches_named_cloudflare_incident_and_scope(self):
        fake = FakeProvider([final(''), final(''), final('')])
        question = 'Cloudflare cache purge báo degraded. CLB là khách hàng không thuộc FedRAMP. Incident wp49bp8bqo6c có chứng minh CLB bị sự cố này ảnh hưởng không? Hãy chỉ ra thông báo cụ thể, trạng thái và nguồn.'
        result = run_agent(question, fake, StatusTools(), max_steps=4)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('Fedramp Customers have Delayed Purges', result['answer'])
        self.assertIn('Non-fedramp customers are not impacted', result['answer'])
        status_call = next(x for x in result['trace'] if x.get('event') == 'tool' and x.get('name') == 'get_status')
        self.assertEqual(status_call['arguments'].get('component'), 'cache purge')

    def test_blank_model_historical_all_request_discloses_limit_and_lists_sample(self):
        fake = FakeProvider([final(''), final(''), final('')])
        question = 'Tôi cần danh sách đầy đủ tất cả incident GitHub Actions trong năm 2025. Hãy tìm dữ liệu và nói rõ độ đầy đủ.'
        result = run_agent(question, fake, StatusTools(), max_steps=4)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('không thể xác nhận danh sách đầy đủ cho giai đoạn 2025', result['answer'])
        self.assertIn('Incident record trong kết quả trả về', result['answer'])

    def test_nonempty_historical_full_list_answer_must_disclose_snapshot_limit(self):
        question='Liệt kê toàn bộ incident trong năm 2025; nói rõ nếu không thể đảm bảo danh sách đầy đủ.'
        fake=FakeProvider([
            final('Incident with Actions — 2026-11-05 — resolved.'),
            final('Incident with Actions — 2026-11-05 — resolved.'),
        ])

        result=run_agent(question,fake,StatusTools(),max_steps=4)

        self.assertEqual(result['status'],'completed')
        self.assertIn('validation_historical_completeness',[e['event'] for e in result['trace']])
        self.assertIn('fallback_historical_completeness',[e['event'] for e in result['trace']])
        self.assertIn('50 incident gần nhất',result['answer'])
        self.assertIn('không thể xác nhận danh sách đầy đủ',result['answer'])

    def test_blank_out_of_scope_request_does_not_fail_or_call_tools(self):
        class OutOfScopeProvider(FakeProvider):
            def complete(self, messages, schemas):
                self.histories.append(list(messages))
                self.schemas_seen = getattr(self, 'schemas_seen', []) + [schemas]
                if len(self.histories) == 1:
                    return final('')
                if not schemas and 'do not ask a follow-up question' in messages[-1]['content'].lower():
                    return final('Biển xanh vỗ bờ, gió hát khúc xa.\nMây trôi qua sóng, nắng rót chan hòa.')
                return final('')

        fake = OutOfScopeProvider([])
        question = 'Hãy viết bài thơ về biển, đừng kiểm tra trạng thái GitHub hay Cloudflare.'
        result = run_agent(question, fake, StatusTools(), max_steps=3)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('Biển xanh vỗ bờ', result['answer'])
        self.assertTrue(fake.schemas_seen)
        self.assertTrue(all(not schema_set for schema_set in fake.schemas_seen))
        self.assertNotIn('Bạn là trợ lý điều tra trạng thái GitHub và Cloudflare',
                         fake.histories[0][0]['content'])
        self.assertIn('đáp ứng trực tiếp yêu cầu hợp lệ', fake.histories[0][0]['content'])
        self.assertIn('Do not ask a follow-up question', fake.histories[1][-1]['content'])
        self.assertFalse(any(item.get('event') == 'tool' for item in result['trace']))

    def test_explicit_incident_id_overrides_unrelated_recent_incident(self):
        fake = FakeProvider([final(''), final(''), final('')])
        question = 'Cloudflare Spectrum tại Việt Nam bị lỗi; kiểm tra incident Phoenix.'
        result = run_agent(question, fake, StatusTools(), max_steps=4)
        details = [x for x in result['trace'] if x.get('event') == 'tool' and x.get('name') == 'get_incident_details']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(details[0]['arguments']['incident_id'], 'c60k3g4vsoc1')
        self.assertIn('Spectrum Availability Issue in Phoenix', result['answer'])

    def test_latest_update_of_explicit_incident_is_not_latest_incident_request(self):
        fake = FakeProvider([final(''), final(''), final('')])
        question = 'Xem phần cập nhật mới nhất của incident GitHub h02n9572mx9y và dẫn nguồn.'
        result = run_agent(question, fake, StatusTools(), max_steps=4)
        details = [x for x in result['trace'] if x.get('event') == 'tool'
                   and x.get('name') == 'get_incident_details']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([x['arguments']['incident_id'] for x in details], ['h02n9572mx9y'])
        self.assertFalse(any(x.get('event') == 'validation_latest_incident' for x in result['trace']))

    def test_blank_model_answer_states_causal_limits_and_requested_next_step(self):
        fake = FakeProvider([final(''), final(''), final('')])
        question = 'Cloudflare Spectrum ở Việt Nam bị lỗi, incident Phoenix có gây lỗi này không? Đề nghị bước kiểm tra tiếp theo.'
        result = run_agent(question, fake, StatusTools(), max_steps=4)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('không đủ để xác lập', result['answer'])
        self.assertIn('đối chiếu thời điểm lỗi', result['answer'])

    def test_nonexistent_incident_id_gets_no_fabricated_url_when_model_is_blank(self):
        fake = FakeProvider([final(''), final(''), final('')])
        question = 'Xem incident có mã totally-not-a-real-id vừa làm Cloudflare sập toàn cầu; cho tôi link chính xác.'
        result = run_agent(question, fake, StatusTools(), max_steps=4)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('INCIDENT_NOT_FOUND', result['answer'])
        self.assertNotIn('/incidents/totally-not-a-real-id', result['answer'])

    def test_blank_model_follows_incident_link_when_user_requests_it(self):
        fake = FakeProvider([final(''), final(''), final(''), final('')])
        question = 'Theo liên kết do incident GitHub h02n9572mx9y cung cấp, đọc incident liên quan và đối chiếu với Cloudflare yaa0witbl2me.'
        result = run_agent(question, fake, StatusTools(), max_steps=5)
        detail_calls = [x for x in result['trace'] if x.get('event') == 'tool' and x.get('name') == 'get_incident_details']
        ids = {x['arguments']['incident_id'] for x in detail_calls}
        self.assertEqual(result['status'], 'completed')
        self.assertIn('h02n9572mx9y', ids)
        self.assertIn('xr3myzj7ms51', ids)
        self.assertIn('yaa0witbl2me', ids)
        self.assertIn('githubstatus.com/incidents/xr3myzj7ms51', result['answer'])

    def test_missing_url_gets_revision_within_budget(self):
        url = 'https://stspg.io/pjgptg3cfc6n'
        fake = FakeProvider([tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
                             final('Incident đã xử lý.'), final('Incident đã xử lý. '+url)])
        result = run_agent('Kiểm tra', fake, StatusTools(), max_steps=4)
        self.assertEqual(result['status'], 'completed')
        self.assertIn(url, result['answer'])
        self.assertTrue(any(x['event'] == 'validation_missing_source' for x in result['trace']))
    def test_missing_url_at_budget_limit_is_not_completed(self):
        fake = FakeProvider([tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'), final('Thiếu nguồn')])
        self.assertEqual(run_agent('x', fake, StatusTools(), max_steps=2)['status'], 'max_steps')
    def test_failed_tool_does_not_require_source(self):
        fake = FakeProvider([tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"missing"}'), final('Không tìm được incident')])
        self.assertEqual(run_agent('x', fake, StatusTools())['status'], 'completed')

    def test_failed_provider_status_cannot_be_reported_as_operational(self):
        tools = ScenarioTools('cloudflare_timeout')
        fake = FakeProvider([
            tool_call('gh', 'get_status', '{"provider":"github","component":"Actions"}'),
            tool_call('cf', 'get_status', '{"provider":"cloudflare","component":"Spectrum"}'),
            final('GitHub Actions is operational. Cloudflare Spectrum is operational despite the tool timeout.'),
            final('GitHub Actions is operational. Cloudflare timed out, so I cannot confirm its status.'),
        ])
        result = run_agent('Check GitHub Actions and Cloudflare Spectrum.', fake, tools, max_steps=5)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('cannot confirm', result['answer'])
        self.assertTrue(any(x['event'] == 'validation_unknown_status' for x in result['trace']))

    def test_empty_components_cannot_be_reported_as_no_service_impact(self):
        class EmptyComponentsTools(StatusTools):
            def execute(self, name, args):
                if name == 'get_status':
                    return {'ok': True, 'provider': 'github', 'components': [],
                            'incidents': [{'id': 'case-id', 'name': 'Test incident'}],
                            'source': 'https://www.githubstatus.com'}
                return super().execute(name, args)
        fake = FakeProvider([
            tool_call('status', 'get_status', '{"provider":"github"}'),
            final('components rỗng nên không có dịch vụ bị ảnh hưởng.'),
            final('components rỗng không chứng minh rằng không có dịch vụ nào bị ảnh hưởng.'),
        ])
        result = run_agent('Kiểm tra incident GitHub.', fake, EmptyComponentsTools())
        self.assertEqual(result['status'], 'completed')
        self.assertIn('không chứng minh', result['answer'])

    def test_empty_components_guard_allows_nonimpact_claim_quoted_from_incident(self):
        body=('Cloudflare has identified a bug with our purge pipeline impacting fedramp customers. '
              'Stale content may be served until expired. Non-fedramp customers are not impacted.')

        class ScopedIncidentTools(StatusTools):
            def execute(self, name, args):
                if name == 'get_status':
                    return {'ok': True, 'provider': 'cloudflare', 'captured_at': '2026-11-09T03:50:47Z',
                            'overall': {'indicator': 'major', 'description': 'Partial System Outage'},
                            'components': [], 'incidents': [{'id': 'wp49bp8bqo6c', 'name': 'Fedramp Customers have Delayed Purges'}],
                            'source': 'https://www.cloudflarestatus.com'}
                if name == 'get_incident_details':
                    return {'ok': True, 'provider': 'cloudflare', 'id': 'wp49bp8bqo6c',
                            'name': 'Fedramp Customers have Delayed Purges', 'status': 'identified',
                            'updated_at': '2026-11-06T17:59:13Z', 'components': ['CDN Cache Purge'],
                            'updates': [{'status': 'investigating', 'created_at': '2026-11-06T17:47:15Z', 'body': body}],
                            'url': 'https://www.cloudflarestatus.com/incidents/wp49bp8bqo6c'}
                return super().execute(name, args)

        answer=(f'Cloudflare incident: "{body}" CLB không bị ảnh hưởng. '
                'Nguồn: https://www.cloudflarestatus.com/incidents/wp49bp8bqo6c')
        fake=FakeProvider([
            tool_call('s','get_status','{"provider":"cloudflare","component":"cache purge"}'),
            tool_call('d','get_incident_details','{"provider":"cloudflare","incident_id":"wp49bp8bqo6c"}'),
            final(answer), final(answer),
        ])
        question=('Cloudflare cache purge báo degraded. CLB không thuộc FedRAMP. '
                  'Incident wp49bp8bqo6c có ảnh hưởng CLB không?')

        result=run_agent(question,fake,ScopedIncidentTools(),max_steps=6)

        self.assertEqual(result['status'],'completed')
        self.assertIn('CLB không bị ảnh hưởng',result['answer'])
        self.assertFalse(any(e.get('event')=='validation_empty_components' for e in result['trace']))

if __name__ == '__main__':
    unittest.main()
