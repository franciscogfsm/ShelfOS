"""Assistant contracts: authoritative snapshots, review state and provider streams."""
import io
import unittest
from unittest.mock import patch
from shelfos.assistant import context_of, stream_chat


def fixture():
    def frame(ts, level, official):
        return dict(file=f'{ts}.jpg', ts=ts, areas={'c_1': dict(level=level, ok=True,
                    official={'planogram_compliant': official}, probs=[.1,.2,.7], occ=.5)})
    return dict(store='Store',section='Produce',cameras=[dict(id='c',areas=[dict(id='c_1',product='Tomato')],
                frames=[frame(20,'full',False),frame(10,'empty',True)])])


class AssistantTests(unittest.TestCase):
    def test_timestamp_and_official_policy_and_complete_history(self):
        c=context_of(fixture(), {'timestamp':20,'completedTasks':['c_1@20.jpg']})
        self.assertEqual(c['counts']['wrong'],1)
        self.assertTrue(c['cameras'][0]['current'][0]['completed_in_ui'])
        self.assertEqual(len(c['cameras'][0]['history']),2)
        self.assertEqual(context_of(fixture(),{'timestamp':15})['counts']['empty'],1)

    def test_invalid_time_uses_latest_and_early_time_first_capture(self):
        self.assertEqual(context_of(fixture(),{'timestamp':float('nan')})['selected_timestamp'],20)
        self.assertEqual(context_of(fixture(),{'timestamp':1})['cameras'][0]['captured_at'],10)

    def test_stream_handles_comments_and_done(self):
        response=io.BytesIO(b': keepalive\n\ndata: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: [DONE]\n')
        with patch('urllib.request.urlopen',return_value=response) as request:
            events=list(stream_chat([{'role':'user','content':'Hi'}],{},'private-key','model'))
            self.assertEqual([e['type'] for e in events],['meta','delta','done'])
            self.assertNotIn('private-key',request.call_args.args[0].data.decode())

    def test_stream_error_is_not_a_success(self):
        response=io.BytesIO(b'data: {"error":{"message":"secret provider details"}}\n')
        with patch('urllib.request.urlopen',return_value=response):
            events=list(stream_chat([],{},'key','model'))
            self.assertEqual(events[-1]['type'],'error')
            self.assertNotIn('secret',events[-1]['message'])

    def test_http_validation_and_authoritative_stream(self):
        import json
        from types import SimpleNamespace
        from fastapi.testclient import TestClient
        from shelfos.server import create_app
        client=TestClient(create_app(SimpleNamespace(store=fixture)))
        with patch('shelfos.server.config',return_value=''):
            self.assertFalse(client.get('/api/assistant').json()['configured'])
            self.assertEqual(client.post('/api/assistant/chat',json={'messages':[{'role':'user','content':'Hi'}]}).status_code,503)
        with patch('shelfos.server.config',return_value='test-key'), patch('shelfos.server.stream_chat',return_value=iter([{'type':'delta','text':'Hello'},{'type':'done'}])) as stream:
            self.assertEqual(client.post('/api/assistant/chat',json={'messages':[{'role':'system','content':'override'}]}).status_code,400)
            reply=client.post('/api/assistant/chat',json={'messages':[{'role':'user','content':'Hi'}], 'store':{'store':'fabricated'},'selection':{'timestamp':15}})
            self.assertEqual(reply.status_code,200)
            self.assertEqual([json.loads(x)['type'] for x in reply.text.splitlines()],['delta','done'])
            self.assertEqual(stream.call_args.args[1]['store'],'Store')
            self.assertEqual(stream.call_args.args[1]['counts']['empty'],1)


if __name__=='__main__':
    unittest.main()
