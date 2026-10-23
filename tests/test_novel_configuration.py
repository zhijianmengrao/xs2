import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.web.novel_configuration import parse_advisor, parse_configuration
from src.web.novel_assistant import NovelAssistantJobs, _receive_model_reply


class ConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_adviser_completion_budget_is_distinct_from_transport_timeout(self):
        async def complete(awaitable, timeout):
            budgets.append(timeout)
            return await awaitable
        class Model:
            async def ainvoke(self, messages):
                return SimpleNamespace(content=json.dumps({'reply':'方案', 'suggestions':[],
                    'advisor_sections':dict.fromkeys(('direction','hook','writing','risks'),'可阅读内容')}))
        budgets=[]
        with tempfile.TemporaryDirectory() as directory:
            jobs=NovelAssistantJobs()
            with patch('src.web.novel_assistant.create_llm',return_value=Model()) as factory, \
                 patch('src.web.novel_assistant.asyncio.wait_for',side_effect=complete):
                entry=jobs.start(Path(directory),'budget',{'question':'复杂世界设定','purpose':'advisor'})
                await jobs.tasks[entry['id']]
            self.assertEqual(budgets,[600])
            # The transport budget is intentionally the same value as the
            # completion budget: a long streamed answer (e.g. a full-chapter
            # reader_repair) must not be cut off by a shorter per-attempt
            # timeout. See test_novel_repair
            # ::test_full_chapter_repair_can_complete_after_short_analysis_deadline,
            # which pins that requirement.
            self.assertEqual(factory.call_args.kwargs['timeout'],600)
            self.assertTrue(factory.call_args.kwargs['streaming'])

    async def test_streamed_final_answer_preserves_json_whitespace_and_excludes_reasoning(self):
        class StreamModel:
            async def astream(self,messages):
                yield SimpleNamespace(content=[{'type':'reasoning','text':'do not expose this'}])
                yield SimpleNamespace(content='{"reply":"hello ')
                yield SimpleNamespace(content='world", "suggestions": []}')
        updates=[]
        response=await _receive_model_reply(StreamModel(),[],lambda:updates.append(True))
        reply,items=parse_configuration(response.content,'short')
        self.assertEqual(reply,'hello world')
        self.assertEqual(items,[])
        self.assertEqual(updates,[True])

    def test_adviser_requires_readable_four_sections_and_validates_parameter_suggestions(self):
        data={'reply':'推荐先写救援与信任危机。', 'suggestions':[{'key':'genre','value':'末日悬疑'}],
              'advisor_sections':{'direction':'救援起点','hook':'聚集悖论','writing':'限知视角','risks':'阈值规则需要澄清'}}
        reply, items, sections=parse_advisor(json.dumps(data,ensure_ascii=False),'serial')
        self.assertIn('信任危机',reply)
        self.assertEqual(len(sections),4)
        self.assertEqual(items[0]['label'],'题材')
        data['advisor_sections']['risks']={'raw':'json'}
        with self.assertRaises(ValueError):parse_advisor(json.dumps(data),'serial')

    async def test_adviser_history_preserves_original_brief_and_does_not_create_world_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            captured=[]
            class Model:
                async def ainvoke(self,messages):
                    captured.extend(messages)
                    return SimpleNamespace(content=json.dumps({'reply':'建议', 'suggestions':[],
                        'advisor_sections':{'direction':'方向','hook':'看点','writing':'写法','risks':'风险'}}))
            jobs=NovelAssistantJobs()
            with patch('src.web.novel_assistant.create_llm',return_value=Model()):
                entry=jobs.start(root,'advisor-test',{'question':'补充问题','purpose':'advisor',
                    'project':{'mode':'serial','values':{},'advisor_brief':'原始设定：72-120小时潜伏期'}})
                await jobs.tasks[entry['id']]
            result=jobs.history(root)[0]
            self.assertEqual(result['purpose'],'advisor')
            self.assertIn('72-120小时',result['configuration_base']['advisor_brief'])
            self.assertIn('最多追问一到两个问题',captured[0][1])
            self.assertFalse((root/'meta/world_foundation.md').exists())

    def test_filters_unsafe_keys_and_invalid_scope_counts_and_words(self):
        data = {'reply': '建议用第一人称。', 'suggestions': [
            {'key': 'narrative_pov', 'value': 'first_person', 'reason': '限制信息'},
            {'key': 'target_word_count', 'value': '5000～7000'},
            {'key': 'conflict_point_count', 'value': '51'},
            {'key': 'foreshadowing_count', 'value': True},
            {'key': 'conflict_plan_mode', 'value': 'serial_opening'},
            {'key': 'output_path', 'value': '../other-book.txt'},
            {'key': 'target_word_count', 'value': '7000-5000'},
            {'key': 'estimated_length', 'value': '短篇全文约5000字'},
        ]}
        answer, items = parse_configuration('```json\n' + json.dumps(data) + '\n```', 'short')
        self.assertEqual(answer, '建议用第一人称。')
        self.assertEqual({item['key']: item['value'] for item in items},
                         {'narrative_pov': 'first_person', 'target_word_count': '5000-7000', 'estimated_length': '短'})

    def test_malformed_envelope_cannot_become_a_readable_json_answer(self):
        for data in ['not json', '{"reply":{"raw":1}}', '{"reply":"方案","suggestions":{}}']:
            with self.assertRaises(ValueError):
                parse_configuration(data, 'short')

    async def test_model_configuration_is_durable_and_existing_facts_are_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'meta').mkdir()
            (root / 'meta/world_foundation.md').write_text('已确定世界事实', encoding='utf-8')
            captured = []
            class Model:
                model_name = 'test-model'
                async def ainvoke(self, messages):
                    captured.extend(messages)
                    return SimpleNamespace(content=json.dumps({'reply': '推荐三处递进冲突。',
                        'suggestions': [{'key': 'conflict_point_count', 'value': '3'}]}, ensure_ascii=False))
            jobs = NovelAssistantJobs()
            payload = {'question': '规划末日短篇', 'purpose': 'configure',
                       'project': {'mode': 'short', 'values': {'genre': '末日'}}}
            with patch('src.web.novel_assistant.create_llm', return_value=Model()):
                entry = jobs.start(root, 'configuration-test', payload)
                await jobs.tasks[entry['id']]
            stored = NovelAssistantJobs().history(root)[0]
            self.assertEqual(stored['reply'], '推荐三处递进冲突。')
            self.assertTrue(stored['configuration_base']['has_story_facts'])
            self.assertEqual(stored['suggestions'][0]['label'], '冲突点数量')
            self.assertIn('target_word_count指整篇字数', captured[0][1])
            self.assertEqual((root / 'meta/world_foundation.md').read_text(encoding='utf-8'), '已确定世界事实')

    async def test_bad_model_output_reports_failure_without_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            class Model:
                async def ainvoke(self, messages):
                    return SimpleNamespace(content='{"reply":broken}')
            jobs = NovelAssistantJobs()
            with patch('src.web.novel_assistant.create_llm', return_value=Model()):
                entry = jobs.start(Path(directory), 'bad-configuration', {'question': '配置', 'purpose': 'configure'})
                await jobs.tasks[entry['id']]
            stored = jobs.history(Path(directory))[0]
            self.assertEqual(stored['status'], 'failed')
            self.assertEqual(stored['error_code'], 'configuration_format')
            self.assertNotIn('suggestions', stored)
