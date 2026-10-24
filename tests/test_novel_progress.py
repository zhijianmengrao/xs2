import json
from pathlib import Path
import tempfile
import unittest
from src.web.novel_progress import progress, STAGES


class NovelProgressTests(unittest.TestCase):
    def test_real_artifacts_tasks_and_revision_invalidate_old_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'book'; flows = Path(directory)/'workflows'
            paths = ['meta/world_foundation.md', 'meta/character_profiles.md', 'meta/story_plan.md',
                     'outline/near_term_outline.md', 'story/0001/chapter.md', 'quality/reader_report.json',
                     'story/0001/diff_story_confirmed.md', 'export/manuscript.md']
            for rel in paths:
                p=root/rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('{}' if rel.endswith('.json') else '正文', encoding='utf-8')
            state={'mode':'short', 'values':{'chapter_number':'0001'}, 'refs':{}}
            for i,(stage,_) in enumerate(STAGES):
                state['refs'][stage]={'workflow_id':stage, 'task_id':'task'}
                p=flows/stage/'tasks/task.json'; p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(json.dumps({'status':'completed','started_at':f'2026-10-07T10:{i:02d}:00','completed_at':f'2026-10-07T10:{i:02d}:30'}))
            self.assertEqual(progress(root,state,flows)['percent'],100)
            task=flows/'polish/tasks/task.json'
            task.write_text(json.dumps({'status':'running','started_at':'2026-10-07T11:00:00'}))
            actual=progress(root,state,flows)
            self.assertEqual(actual['percent'],56)
            self.assertIn('润色正文处理中',actual['label'])
            self.assertFalse(actual['export_current'])
            self.assertTrue(actual['can_download'])

    def test_chapter_count_does_not_imply_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'book'; root.mkdir()
            p=root/'story/0001/chapter.md';p.parent.mkdir(parents=True);p.write_text('正文', encoding='utf-8')
            result=progress(root,{'mode':'serial','values':{'chapter_number':'../0001'}},Path(directory)/'flows')
            self.assertEqual(result['chapter_count'],1)
            self.assertEqual(result['percent'],0)
            self.assertFalse(result['can_download'])


if __name__ == '__main__': unittest.main()
