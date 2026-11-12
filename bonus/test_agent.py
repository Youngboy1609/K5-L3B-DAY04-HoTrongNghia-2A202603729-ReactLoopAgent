"""Kiểm tra agent với tools bonus mà không gọi LLM API."""
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent import run_agent, _render_observed_summary
from bonus.tools import BonusTools


def call(call_id,name,args):
    raw=json.dumps(args)
    c={'id':call_id,'name':name,'arguments':raw}
    m={'role':'assistant','content':None,'tool_calls':[{'id':call_id,'type':'function','function':{'name':name,'arguments':raw}}]}
    return {'message':m,'calls':[c],'finish':'tool_calls','usage':{}}

def final(answer='Đã kiểm tra'):
    return {'message':{'role':'assistant','content':answer},'calls':[],'finish':'stop','usage':{}}


class ScriptedProvider:
    def __init__(self,responses): self.responses=iter(responses); self.histories=[]; self.schemas=[]
    def complete(self,messages,schemas):
        self.histories.append(list(messages));self.schemas.append(schemas)
        return next(self.responses)


class BonusAgentTests(unittest.TestCase):
    def test_timeline_fallback_keeps_requested_evidence_beyond_first_three_updates(self):
        status = {'vercel': {'overall': {'description': 'All Systems Operational'},
                             'captured_at': '2026-11-12T08:00:00Z',
                             'source': 'https://status.example.test'}}
        for position in (3, 6):
            with self.subTest(position=position):
                updates = [{'created_at': f'2026-11-11T{20-i:02}:00:00Z',
                            'body': 'Deployment backlog is being processed.'} for i in range(7)]
                updates[position]['body'] = 'Certificate renewal failed; rotate the expired certificate.'
                detail = {'provider': 'vercel', 'id': 'synthetic-incident', 'status': 'resolved',
                          'url': 'https://status.example.test/incidents/synthetic-incident',
                          'updates': updates, 'next_offset': 7}

                answer = _render_observed_summary(status, [detail], question=
                    'Which timeline update reports the certificate renewal failure?')

                self.assertIn(updates[position]['body'], answer)
                self.assertIn(updates[position]['created_at'], answer)
                self.assertIn(detail['url'], answer)
                self.assertLessEqual(answer.count('Update '), 3)
                self.assertIn('offset 7', answer)
                self.assertEqual(detail['updates'], updates)

    def test_invalid_timeline_format_is_retried_once_with_integer_defaults(self):
        tools=BonusTools(scenario='format_once')
        details=BonusTools().execute('get_incident_details',{
            'provider':'npm','incident_id':'cc0t2r4403sy'})
        answer=(f'INVALID_ARGUMENTS was corrected and retried. Incident resolved. Source: {details["url"]}.')
        p=ScriptedProvider([
            call('a','get_incident_details',{'provider':'npm','incident_id':'cc0t2r4403sy'}),
            final(answer),
        ])
        result=run_agent('Read npm incident details.',p,tools,max_steps=4)
        detail_events=[x for x in result['trace'] if x.get('event')=='tool' and x.get('name')=='get_incident_details']
        self.assertEqual([x['result'].get('error') for x in detail_events],['INVALID_ARGUMENTS',None])
        self.assertEqual(detail_events[1]['arguments']['offset'],0)
        self.assertEqual(detail_events[1]['arguments']['limit'],2)

    def test_invalid_format_in_validation_fallback_is_retried_once(self):
        tools=BonusTools(scenario='format_once')
        details=BonusTools().execute('get_incident_details',{
            'provider':'npm','incident_id':'cc0t2r4403sy'})
        answer=(f'INVALID_ARGUMENTS was corrected and retried. Incident resolved. Source: {details["url"]}.')
        question=('Xem chi tiết npm incident cc0t2r4403sy. Nếu tool báo tham số offset/limit '
                  'sai định dạng, sửa lại, đọc kết quả và dẫn nguồn.')
        p=ScriptedProvider([final(''),final(''),final(answer)])
        result=run_agent(question,p,tools,max_steps=5)
        detail_events=[x for x in result['trace'] if x.get('event')=='tool'
                       and x.get('name')=='get_incident_details']
        self.assertEqual([x['result'].get('error') for x in detail_events],['INVALID_ARGUMENTS',None])
        self.assertEqual(detail_events[1]['arguments']['offset'],0)
        self.assertEqual(detail_events[1]['arguments']['limit'],2)

    def test_empty_model_answer_fallback_discloses_recovered_invalid_arguments(self):
        tools=BonusTools(scenario='format_once')
        question=('Xem chi tiết npm incident cc0t2r4403sy. Nếu tool báo tham số offset/limit '
                  'sai định dạng, sửa lại, đọc kết quả và dẫn nguồn.')
        p=ScriptedProvider([
            call('s','get_npm_status',{'component':'incident'}),
            final(''),
            final(''),
        ])

        result=run_agent(question,p,tools,max_steps=5)

        detail_events=[x for x in result['trace'] if x.get('event')=='tool'
                       and x.get('name')=='get_incident_details']
        self.assertEqual([x['result'].get('error') for x in detail_events],['INVALID_ARGUMENTS',None])
        self.assertEqual(result['status'],'completed')
        self.assertIn('INVALID_ARGUMENTS',result['answer'])
        self.assertIn('offset/limit',result['answer'])
        self.assertIn('sửa',result['answer'].casefold())

    def test_repeated_omission_of_argument_recovery_is_filled_from_trace(self):
        tools = BonusTools(scenario='format_once')
        args = {'provider': 'npm', 'incident_id': 'cc0t2r4403sy'}
        detail = BonusTools().execute('get_incident_details', args)
        answer = 'Incident resolved. Source: ' + detail['url']
        provider = ScriptedProvider([call('d', 'get_incident_details', args),
                                     final(answer), final(answer)])
        result = run_agent('Read incident details.', provider, tools, max_steps=4)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('INVALID_ARGUMENTS', result['answer'])
        self.assertIn('offset/limit', result['answer'])
        self.assertIn(detail['url'], result['answer'])
        self.assertEqual(len(provider.histories), 3)

    def test_batch_tool_results_precede_automatic_format_retry(self):
        tools=BonusTools(scenario='format_once')
        detail_call=call('d','get_incident_details',{'provider':'npm','incident_id':'cc0t2r4403sy'})
        status_call=call('s','get_npm_status',{})
        combined={
            'message': {'role':'assistant','content':None,
                        'tool_calls':detail_call['message']['tool_calls']+status_call['message']['tool_calls']},
            'calls': detail_call['calls']+status_call['calls'], 'finish':'tool_calls','usage':{},
        }
        details=BonusTools().execute('get_incident_details',{
            'provider':'npm','incident_id':'cc0t2r4403sy'})
        answer=f'INVALID_ARGUMENTS corrected and retried. Source: {details["url"]}.'
        p=ScriptedProvider([combined,final(answer)])
        result=run_agent('Check npm incident.',p,tools,max_steps=4)
        messages=p.histories[1]
        retry_index=next(i for i,m in enumerate(messages) if m.get('role')=='assistant'
                         and any(c.get('id')=='d-format-retry' for c in m.get('tool_calls',[])))
        original_results=[i for i,m in enumerate(messages) if m.get('role')=='tool'
                          and m.get('tool_call_id') in {'d','s'}]
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len(original_results),2)
        self.assertGreater(retry_index,max(original_results))

    def test_timeline_request_reads_next_page_when_first_page_is_incomplete(self):
        tools=BonusTools()
        args={'provider':'vercel','incident_id':'sps6n39gm4sg','offset':0,'limit':2}
        page_two=tools.execute('get_incident_details',{**args,'offset':2})
        question=('Tra timeline Vercel incident sps6n39gm4sg: thông báo nào nói '
                  'các build GitHub-connected vẫn lỗi do upstream?')
        p=ScriptedProvider([
            final(''),
            final(''),
            final(''),
        ])
        result=run_agent(question,p,tools,max_steps=5)
        detail_events=[x for x in result['trace'] if x.get('event')=='tool' and x.get('name')=='get_incident_details']
        self.assertEqual([x['arguments'].get('offset',0) for x in detail_events],[0,2])
        self.assertTrue(any('GitHub-connected' in u.get('body','')
                            for u in page_two.get('updates',[])))
        self.assertEqual(result['status'], 'completed')
        self.assertIn('GitHub-connected', result['answer'])
        self.assertIn('2026-10-12T16:10:48.923Z', result['answer'])
        self.assertIn(page_two['url'], result['answer'])

    def test_nonempty_timeline_answer_retains_requested_update_evidence(self):
        tools = BonusTools()
        args = {'provider': 'vercel', 'incident_id': 'sps6n39gm4sg'}
        detail = BonusTools().execute('get_incident_details', args)
        partial = 'No failures were reported. Vercel is operational. Incident source: ' + detail['url']
        provider = ScriptedProvider([final(''), final(''), final(partial)])
        result = run_agent('Tra timeline Vercel incident sps6n39gm4sg: thông báo nào nói '
                           'build GitHub-connected vẫn lỗi do upstream?', provider, tools, max_steps=5)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('GitHub-connected', result['answer'])
        self.assertIn('2026-10-12T16:10:48.923Z', result['answer'])
        self.assertIn('resolved', result['answer'])
        self.assertIn(detail['url'], result['answer'])
        self.assertNotIn('No failures were reported.', result['answer'])

    def test_persistent_rate_limit_stops_before_fourth_model_tool_request(self):
        tools = BonusTools(scenario='rate_limit_always')
        provider = ScriptedProvider([
            call('gh', 'get_github_status', {}),
            call('v1', 'get_vercel_status', {}),
            call('v2', 'get_vercel_status', {}),
            call('v3', 'get_vercel_status', {}),
            call('v4', 'get_vercel_status', {}),
            final('Vercel status unknown.'),
        ])
        result = run_agent('Check status GitHub and Vercel.', provider, tools, max_steps=8)
        vercel_calls = [e for e in result['trace'] if e.get('name') == 'get_vercel_status']
        self.assertEqual(len(vercel_calls), 3)
        self.assertEqual(len(provider.histories), 4)
        self.assertEqual(result['status'], 'completed')
        self.assertIn('chưa xác nhận', result['answer'])
        self.assertIn('github', result['answer'])

    def test_latest_incident_request_replaces_a_stale_model_selection(self):
        tools=BonusTools()
        status=tools.execute('get_npm_status',{'component':'package publishing'})
        latest_id=status['incidents'][0]['id']
        latest=BonusTools().execute('get_incident_details',{
            'provider':'npm','incident_id':latest_id})
        stale=BonusTools().execute('get_incident_details',{
            'provider':'npm','incident_id':'xfp75s9j3bp8'})
        question='Xem incident mới nhất của npm package publishing, scope và timeline.'
        p=ScriptedProvider([
            call('s','get_npm_status',{'component':'package publishing'}),
            call('d','get_incident_details',{'provider':'npm','incident_id':'xfp75s9j3bp8'}),
            final('Incident cũ đã resolved. Source: '+stale['url']),
            final('Incident mới nhất đã resolved. Source: '+latest['url']),
        ])
        result=run_agent(question,p,tools,max_steps=6)
        ids=[x['arguments'].get('incident_id') for x in result['trace']
             if x.get('event')=='tool' and x.get('name')=='get_incident_details']
        self.assertIn(latest_id,ids)

    def test_bonus_schemas_and_system_prompt(self):
        t=BonusTools();p=ScriptedProvider([final()])
        self.assertEqual(run_agent('Kiểm tra',p,t)['status'],'completed')
        names={x['function']['name'] for x in p.schemas[0]}
        self.assertTrue({'get_github_status','get_cloudflare_status','get_vercel_status','get_npm_status','get_digitalocean_status'}.issubset(names))
        self.assertIn('DigitalOcean',p.histories[0][0]['content'])
        self.assertIn('một dòng riêng cho từng provider',p.histories[0][0]['content'])
    def test_429_observation_returns_to_model(self):
        t=BonusTools(scenario='rate_limit_once')
        status=BonusTools().execute('get_vercel_status',{})
        answer=(f'First request returned 429; retry succeeded. Snapshot: {status["captured_at"]}. '
                f'Source: {status["source"]}.')
        p=ScriptedProvider([call('a','get_vercel_status',{}),call('b','get_vercel_status',{}),final(answer)])
        result=run_agent('Kiểm tra',p,t,max_steps=5)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(json.loads(p.histories[1][-1]['content'])['error'],'RATE_LIMITED')
        self.assertEqual(json.loads(p.histories[2][-1]['content'])['provider'],'vercel')
        self.assertIn('429',result['answer'])
    def test_invalid_arguments_observation_returns_to_model(self):
        t=BonusTools()
        bad={'provider':'npm','incident_id':'cc0t2r4403sy','offset':'zero'}
        good={'provider':'npm','incident_id':'cc0t2r4403sy','offset':0}
        details=t.execute('get_incident_details',good)
        corrected='Lỗi INVALID_ARGUMENTS do sai định dạng offset đã được sửa; chi tiết incident. Nguồn: '+details['url']
        p=ScriptedProvider([call('a','get_incident_details',bad),call('b','get_incident_details',good),
                            final('Nguồn: '+details['url']),final(corrected)])
        result=run_agent('Kiểm tra',p,t,max_steps=5)
        self.assertEqual(result['status'],'completed')
        observations=[json.loads(message['content']) for message in p.histories[1]
                      if message.get('role')=='tool']
        self.assertEqual(observations[0]['error'],'INVALID_ARGUMENTS')
        self.assertTrue(observations[-1]['ok'])
        self.assertTrue(any(x['event']=='validation_argument_recovery' for x in result['trace']))

    def test_bonus_incident_answer_must_include_observed_source(self):
        t=BonusTools()
        args={'provider':'vercel','incident_id':'sps6n39gm4sg'}
        details=t.execute('get_incident_details',args)
        p=ScriptedProvider([call('a','get_incident_details',args),final('Incident đã resolved.'),
                            final('Incident đã resolved. Nguồn: '+details['url'])])
        result=run_agent('Xem incident',p,t,max_steps=4)
        self.assertEqual(result['status'],'completed')
        self.assertIn(details['url'],result['answer'])
        self.assertTrue(any(x['event']=='validation_missing_source' for x in result['trace']))

    def test_recovered_rate_limit_answer_reports_retry_time_and_source(self):
        t=BonusTools(scenario='rate_limit_once')
        status=BonusTools().execute('get_vercel_status',{})
        pretty_timestamp=(status['captured_at'].replace('-', '‑').replace('T', ' T')
                          .replace('+00:00', ' +00:00'))
        corrected=(f'**Initial request** returned a rate-limited response (HTTP 429).\n\n'
                   f'**Successful retry** returned a status snapshot with captured_at '
                   f'{pretty_timestamp} and source URL {status["source"]}.')
        p=ScriptedProvider([call('a','get_vercel_status',{}),call('b','get_vercel_status',{}),
                            final('Vercel is All Systems Operational.'),final(corrected)])
        result=run_agent('Check Vercel status and source.',p,t,max_steps=5)
        self.assertEqual(result['status'],'completed')
        self.assertIn('429',result['answer'])
        self.assertIn(pretty_timestamp,result['answer'])
        self.assertIn(status['source'],result['answer'])
        self.assertTrue(any(x['event']=='validation_recovered_status' for x in result['trace']))

    def test_recovery_timestamp_accepts_unicode_and_space_instead_of_t(self):
        t=BonusTools(scenario='rate_limit_once')
        status=BonusTools().execute('get_vercel_status',{})
        pretty_timestamp=(status['captured_at'].replace('-', '‑').replace('T', ' ')
                          .replace('+00:00', ' +00:00'))
        answer=(f'Vercel first returned 429, then retry succeeded. Snapshot {pretty_timestamp}. '
                f'Source: {status["source"]}.')
        p=ScriptedProvider([call('a','get_vercel_status',{}),call('b','get_vercel_status',{}),final(answer)])
        result=run_agent('Check Vercel status.',p,t,max_steps=5)
        self.assertEqual(result['status'],'completed')
        self.assertFalse(any(x['event']=='validation_recovered_status' for x in result['trace']))

    def test_recovery_validation_does_not_repeat_the_same_revision(self):
        t=BonusTools(scenario='rate_limit_once')
        p=ScriptedProvider([call('a','get_vercel_status',{}),call('b','get_vercel_status',{}),
                            final('Vercel is operational.'),final('Still operational.'),
                            final('Still operational.')])
        result=run_agent('Check Vercel status.',p,t,max_steps=5)
        self.assertEqual(result['status'],'completed')
        status = BonusTools().execute('get_vercel_status', {})
        self.assertIn(status['captured_at'], result['answer'])
        self.assertIn(status['source'], result['answer'])
        self.assertIn('429', result['answer'])
        self.assertTrue(any(x['event']=='fallback_recovered_status' for x in result['trace']))
        self.assertEqual(sum(x['event']=='validation_recovered_status' for x in result['trace']),2)
        self.assertEqual(len(p.histories),4)

    def test_malformed_channel_suffix_uses_exact_schema_tool_name(self):
        tools=BonusTools()
        malformed=call('a','get_cloudflare_status<|channel|>commentary',{})
        result=run_agent('Check Cloudflare status.',ScriptedProvider([malformed,final('Cloudflare status checked.')]),tools)
        self.assertEqual(result['status'],'completed')
        tool_events=[x for x in result['trace'] if x['event']=='tool']
        self.assertEqual(tool_events[0]['name'],'get_cloudflare_status')
        self.assertEqual(tool_events[0]['raw_name'],'get_cloudflare_status<|channel|>commentary')
        self.assertTrue(tool_events[0]['result'].get('overall'))

    def test_scope_question_requires_incident_details_for_each_provider(self):
        tools=BonusTools()
        status_calls=[]
        details_calls=[]
        sources={}
        status_results={}
        for provider in ['vercel','npm']:
            status_result=BonusTools().execute(f'get_{provider}_status',{})
            status_results[provider]=status_result
            incident=status_result['incidents'][0]
            args={'provider':provider,'incident_id':incident['id']}
            detail=BonusTools().execute('get_incident_details',args)
            sources[provider]=detail['url']
            status_calls.extend(call(f's-{provider}','get_'+provider+'_status',{} )['calls'])
            details_calls.extend(call(f'd-{provider}','get_incident_details',args)['calls'])
        combined_status={'message':{'role':'assistant','content':None,'tool_calls':[]},
                         'calls':status_calls,'finish':'tool_calls','usage':{}}
        combined_status['message']['tool_calls']=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':c['arguments']}} for c in status_calls]
        combined_details={'message':{'role':'assistant','content':None,'tool_calls':[]},
                          'calls':details_calls,'finish':'tool_calls','usage':{}}
        combined_details['message']['tool_calls']=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':c['arguments']}} for c in details_calls]
        answer='Vercel and npm incident scopes and timelines. '+ ' '.join(sources.values())
        status_summary=' '.join(f'{name}: {status_results[name]["captured_at"]} {status_results[name]["source"]}' for name in ['vercel','npm'])
        p=ScriptedProvider([combined_status,final(status_summary),combined_details,final(answer)])
        result=run_agent('Check status and compare latest Vercel and npm incident scope and timeline.',p,tools,max_steps=6)
        self.assertEqual(result['status'],'completed')
        self.assertTrue(any(x['event']=='validation_missing_incident_details' for x in result['trace']), result['trace'])
        detailed={x['arguments']['provider'] for x in result['trace'] if x['event']=='tool' and x['name']=='get_incident_details'}
        self.assertEqual(detailed,{'vercel','npm'})

    def test_status_summary_checks_every_named_provider(self):
        tools=BonusTools()
        providers=['github','vercel','npm']
        snapshots={p:BonusTools().execute(f'get_{p}_status',{}) for p in providers}
        remaining=[]
        for p in providers[1:]:
            remaining.append(call(f'{p}-call',f'get_{p}_status',{}))
        combined=remaining[0]
        for item in remaining[1:]:
            combined['calls'].extend(item['calls'])
            combined['message']['tool_calls'].extend(item['message']['tool_calls'])
        answer='\n'.join(f'{p}: {snapshots[p]["overall"]["indicator"]}; {snapshots[p]["captured_at"]}; {snapshots[p]["source"]}' for p in providers)
        p=ScriptedProvider([call('gh-call','get_github_status',{}),final('GitHub status only.'),combined,final(answer)])
        result=run_agent('Summarize status for GitHub, Vercel, and npm.',p,tools,max_steps=5)
        self.assertEqual(result['status'],'completed')
        self.assertTrue(any(x['event']=='validation_missing_status_tools' for x in result['trace']))
        called={x['name'] for x in result['trace'] if x['event']=='tool'}
        self.assertTrue({'get_github_status','get_vercel_status','get_npm_status'}.issubset(called))

    def test_partial_multi_status_answer_is_left_for_eval_rubric(self):
        tools=BonusTools()
        providers=['github','vercel','npm']
        snapshots={name:BonusTools().execute(f'get_{name}_status',{}) for name in providers}
        calls=[call(f'id-{name}',f'get_{name}_status',{}) for name in providers]
        all_calls=[x['calls'][0] for x in calls]
        combined={'message':{'role':'assistant','content':None,'tool_calls':[
                    {'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':c['arguments']}}
                    for c in all_calls]},'calls':all_calls,'finish':'tool_calls','usage':{}}
        partial=f'GitHub: {snapshots["github"]["captured_at"]} {snapshots["github"]["source"]}'
        p=ScriptedProvider([combined,final(partial)])
        result=run_agent('Summarize status for GitHub, Vercel, and npm.',p,tools,max_steps=5)
        self.assertEqual(result['status'],'completed')
        self.assertFalse(any(x['event']=='validation_missing_status_evidence' for x in result['trace']))

if __name__=='__main__': unittest.main()
