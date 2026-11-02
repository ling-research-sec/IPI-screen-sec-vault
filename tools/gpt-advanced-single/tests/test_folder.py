"""Exact media selection must never depend on list order or thumb coordinates."""
from unittest import TestCase
from unittest.mock import patch
from test_flow import Phone
from round_flow import Flow
from android import Problem
class DirectCases(TestCase):
    def test_exact_directory_filename_and_uri(self):
        d=Phone();d.name=d.cat.files[40,1]
        with patch.object(d,'shell',wraps=d.shell) as shell:
            Flow(d,d.cat,40,1,lambda _:None).open_file()
        where=next(c.args[-1] for c in shell.call_args_list if c.args[:2]==('content','query'))
        self.assertEqual(where,"relative_path='Pictures/GPT_Advanced/' AND _display_name='097_f40-g01.png'")
        args=d.sent[0][1]
        self.assertIn('content://media/external_primary/images/media/123',args)
        self.assertFalse(any('swipe' in a for _,a in d.sent))
    def test_missing_ambiguous_or_failed_index_stops(self):
        for rows in ('No result found.','Row: 0 _id=1\nRow: 1 _id=2','Error'):
            d=Phone()
            with patch.object(d,'shell',return_value=rows),self.assertRaises(Problem):
                Flow(d,d.cat,16,1,lambda _:None).open_file()
            self.assertEqual(d.sent,[])
