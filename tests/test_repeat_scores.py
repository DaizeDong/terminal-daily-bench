"""Majority scores display one sample SD of the recorded run accuracies."""
import copy
import json
from pathlib import Path
import re
import shutil
import statistics
import subprocess

import pytest

from tools.make_fixtures import repeat_score_fixture

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')


def run_stats(day, task_ids=None):
    if not NODE:
        pytest.skip('Node is required to execute the shipped score helpers')
    script = r'''
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
global.window={TDB:{pct:x=>(100*x).toFixed(1)+'%'}};
vm.runInThisContext(fs.readFileSync('docs/assets/tdb-data.js','utf8'));
const T=window.TDB, matrix=input.day.matrix;
const result=matrix.rows.map(row=>{
 const cols=input.tasks===null?row.g.map((_,i)=>i):input.tasks.map(id=>matrix.tasks.indexOf(id));
 const measured=cols.filter(i=>row.g[i]===0||row.g[i]===1);
 const solved=measured.reduce((sum,i)=>sum+row.g[i],0);
 const repeat=T.resultStats(input.day,row.model,matrix.scaffold,input.tasks===null?undefined:input.tasks);
 return {repeat,estimate:T.scoreEstimate(solved,measured.length,repeat),html:T.scoreCell(solved,measured.length,repeat)};
});
process.stdout.write(JSON.stringify(result));
'''
    proc = subprocess.run([NODE, '-e', script], input=json.dumps({'day': day, 'tasks': task_ids}),
                          cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_majority_score_and_sample_sd_use_distinct_statistics():
    day = repeat_score_fixture()['day']
    result = run_stats(day)
    for row, actual in zip(day['matrix']['rows'], result):
        rates = [sum(x for x in values if x is not None) / 3 for values in row['trials']]
        assert actual['repeat']['mean'] == pytest.approx(statistics.mean(rates))
        assert actual['repeat']['sd'] == pytest.approx(statistics.stdev(rates))
        assert actual['repeat']['min'] == min(rates)
        assert actual['repeat']['max'] == max(rates)
        assert actual['repeat']['n'] == 3
        assert actual['repeat']['runs'] == 3
        center = sum(value for value in row['g'] if value is not None) / 3
        sd = statistics.stdev(rates)
        assert actual['estimate'] == pytest.approx({
            'p': center, 'sd': sd, 'lo': max(0, center - sd),
            'hi': min(1, center + sd), 'runs': 3,
        })
        inline = re.search(r'<strong class="tabular-nums">([^<]+)</strong>'
                           r'<span class="tdb-acc-sd">([^<]+)</span>', actual['html'])
        assert inline
        assert inline.group(1) == f"{actual['estimate']['p'] * 100:.1f}%"
        assert inline.group(2) == f'± {sd * 100:.1f}%'
        assert actual['html'].count('±') == 1
        assert 'tdb-acc-range-value' not in actual['html'] and '–' not in actual['html']
        assert '95%' not in actual['html'] and 'confidence' not in actual['html']
    assert result[1]['repeat']['sd'] == 0
    assert result[1]['estimate']['p'] == 0
    assert result[1]['estimate']['lo'] == result[1]['estimate']['hi'] == 0
    assert 'left:0.00%;width:0.00%' in result[1]['html']
    assert sum(day['matrix']['rows'][1]['g'][:3]) == 0


def test_selected_capability_recomputes_majority_and_sample_sd_on_its_tasks():
    day = repeat_score_fixture()['day']
    result = run_stats(day, day['matrix']['tasks'][:2])
    for row, actual in zip(day['matrix']['rows'], result):
        rates = [sum(values[:2]) / 2 for values in row['trials']]
        assert actual['repeat']['n'] == 2
        assert actual['repeat']['trialRates'] == rates
        assert actual['repeat']['sd'] == pytest.approx(statistics.stdev(rates))
        center, sd = sum(row['g'][:2]) / 2, statistics.stdev(rates)
        assert actual['estimate'] == pytest.approx({
            'p': center, 'sd': sd, 'lo': max(0, center - sd), 'hi': min(1, center + sd), 'runs': 3,
        })


def test_zero_sd_is_displayed_at_majority_even_when_every_run_has_a_different_rate():
    result = run_stats(repeat_score_fixture('outside')['day'])
    for actual, center, bound in zip(result, (1, 0), (2 / 3, 1 / 3)):
        assert actual['repeat']['mean'] == bound and bound != center
        assert actual['estimate'] == {'p': center, 'sd': 0, 'lo': center, 'hi': center, 'runs': 3}
        assert '<span class="tdb-acc-sd">± 0.0%</span>' in actual['html']
        assert f'left:{center * 100:.2f}%;width:0.00%' in actual['html']
        assert f'class="tdb-acc-fill" style="width:{center * 100:.2f}%' in actual['html']
        assert 'tdb-acc-range-value' not in actual['html'] and '95%' not in actual['html']


def test_sd_whiskers_clip_at_zero_and_one_without_changing_the_reported_sd():
    result = run_stats(repeat_score_fixture('sd_bounds')['day'])
    for actual, center, lo, hi in zip(result, (1, 0), (2 / 3, 0), (1, 1 / 3)):
        assert actual['estimate'] == pytest.approx({
            'p': center, 'sd': 1 / 3, 'lo': lo, 'hi': hi, 'runs': 3,
        })
        assert '<span class="tdb-acc-sd">± 33.3%</span>' in actual['html']
        assert f'left:{lo * 100:.2f}%;width:{(hi - lo) * 100:.2f}%' in actual['html']


@pytest.mark.parametrize('case', ['absent', 'single', 'truncated', 'missing', 'invalid', 'disagrees', 'declared'])
def test_incomplete_or_inconsistent_repeats_never_invent_variation(case):
    day = copy.deepcopy(repeat_score_fixture()['day'])
    row = day['matrix']['rows'][0]
    if case == 'absent':
        del row['trials']
    elif case == 'single':
        row['trials'] = row['trials'][:1]
    elif case == 'truncated':
        row['trials'][0].pop()
    elif case == 'missing':
        row['trials'][0][0] = None
    elif case == 'invalid':
        row['trials'][0][0] = 2
    elif case == 'disagrees':
        row['g'][0] = 0
    else:
        day['aggregation']['trials_per_cell'] = 4
    # The generator may expose the primary matrix in both fields.
    if 'matrices' in day:
        day['matrices'][day['matrix']['scaffold']] = day['matrix']
    actual = run_stats(day)[0]
    assert actual['repeat'] is None
    assert actual['estimate'] == {
        'p': sum(value for value in row['g'] if value is not None) / 3,
        'sd': None, 'lo': None, 'hi': None, 'runs': None,
    }
    assert 'tdb-acc-sd' not in actual['html']
    assert 'tdb-acc-range' not in actual['html']


def test_unmeasured_tasks_have_neither_a_score_nor_a_sample_sd():
    result = run_stats(repeat_score_fixture()['day'], ['task-missing'])
    for actual in result:
        assert actual['repeat'] is None and actual['estimate'] is None
        assert actual['html'] == '<span class="text-muted-foreground">&mdash;</span>'


def test_round_order_does_not_change_majority_or_sample_sd():
    day = repeat_score_fixture()['day']
    before = run_stats(day)
    for row in day['matrix']['rows']:
        row['trials'].reverse()
    after = run_stats(day)
    for a, b in zip(before, after):
        assert a['repeat']['mean'] == b['repeat']['mean']
        assert a['repeat']['sd'] == pytest.approx(b['repeat']['sd'])
        assert a['estimate'] == pytest.approx(b['estimate'])
