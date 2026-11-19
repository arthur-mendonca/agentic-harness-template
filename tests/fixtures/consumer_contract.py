"""Shared smoke scenario executed inside isolated wheel and copied runtimes."""

import contextlib
from hashlib import sha256
import io
import json
from pathlib import Path
import sys

from harness.config import load_config
from harness.installer import init_project
from harness.project import PROJECT_FILES
from harness.project_storage import ProjectGit
from harness.project_update import update_project
from harness.runner import main, run
from harness.specs import SECTIONS


def invoke(root, args, code=0):
    output, errors = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        result = main([*args, '--project', str(root)])
    assert result == code, (args, result, output.getvalue(), errors.getvalue())
    return json.loads(output.getvalue())


def snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob('*') if path.is_file()}


def exercise_modes(root):
    root.mkdir()
    assert init_project(root)['valid']
    expected = {*PROJECT_FILES, '.harness/harness.json'}
    git = ProjectGit(root)
    if not git.active:
        expected.add('.gitignore')
    else:
        git.verify_ignored({'.harness/', 'AGENTS.md'})
    assert set(snapshot(root)) == expected
    preserved = {name: (root / name).read_bytes() for name in PROJECT_FILES}
    before = snapshot(root)
    assert invoke(root, ['sdd', 'new', '--mode', 'off', '--title', 'Direct'])['path'] is None
    assert snapshot(root) == before
    assert not (root / '.harness/tarefas').exists()
    for flags, expected in (
        (['--mode', 'lite'], 'lite'), (['--mode', 'full'], 'full'),
        (['--mode', 'auto', '--assessed-low'], 'lite'),
        (['--mode', 'auto', '--risk', 'service_cost=material'], 'full'),
    ):
        task = invoke(root, ['sdd', 'new', '--title', 'Contract', *flags])
        assert task['mode'] == expected
        folder = root / task['path']
        documents = {'meta.json', 'tarefa.md'} if expected == 'lite' else {'meta.json', 'spec.md', 'plan.md', 'tasks.md'}
        assert {path.name for path in folder.iterdir()} == documents
        assert invoke(root, ['sdd', 'resume', str(task['number'])])['id'] == task['id']
    assert len(invoke(root, ['sdd', 'list'])['tasks']) == 4
    full = invoke(root, ['sdd', 'status', '002'])
    folder = root / full['path']
    content = {
        'Requisitos': '- REQ-001: Preservar o texto atualizado.',
        'Critérios de aceite': '- AC-001 (REQ-001): message.txt contém atualizado.',
        'Verificações planejadas': '- AC-001: Executar acceptance para conferir message.txt.',
        'Passos': '- [x] T-001 (REQ-001, AC-001): Atualizar o texto.',
        'Verificação': '- T-001: Check acceptance confere o conteúdo do arquivo.',
    }
    for name, sections in SECTIONS.items():
        text = '# Consumer contract\n\n' + '\n\n'.join(
            '## ' + heading + '\n' + content.get(heading, 'Cenário local de regressão.') for heading in sections)
        (folder / name).write_text(text + '\n', encoding='utf-8')
    assert invoke(root, ['sdd', 'validate', '002'])['valid']
    assert invoke(root, ['sdd', 'trace', '002'])['requirements'][0]['criteria'][0]['id'] == 'AC-001'
    contract = invoke(root, ['sdd', 'verify', '002'], code=1)['contract']
    (root / 'message.txt').write_text('atualizado', encoding='utf-8')
    old_log = root / '.harness/results/previous.log'
    old_log.write_bytes(b'Previous evidence.\r\n')
    config = load_config(root)
    config['checks'] = {'acceptance': {'state': 'configured', 'command': [sys.executable, '-c',
        "from pathlib import Path; assert Path('message.txt').read_text(encoding='utf-8') == 'atualizado'"],
        'cwd': '.', 'timeout': 10}}
    (root / '.harness/harness.json').write_text(json.dumps(config), encoding='utf-8')
    report, code, path = run(root, ['acceptance'])
    assert code == 0 and report['checks']['acceptance']['status'] == 'passed'
    assessment = {'contract': contract, 'criteria': {'AC-001': {
        'status': 'met', 'reason': 'acceptance reads and asserts the requested text.',
        'evidence': [{'report': path.relative_to(root).as_posix(), 'check': 'acceptance'}]}},
        'review': {'status': 'not_performed', 'reason': 'Optional independent review unavailable in this deterministic smoke test.'}}
    assessment_path = root / 'assessment.json'
    assessment_path.write_text(json.dumps(assessment), encoding='utf-8')
    assert invoke(root, ['sdd', 'verify', '002', '--assessment', str(assessment_path)])['ready']
    assert invoke(root, ['sdd', 'set-status', '002', 'completed'])['status'] == 'completed'
    assert old_log.read_bytes() == b'Previous evidence.\r\n'
    assert all((root / name).read_bytes() == data for name, data in preserved.items())


def exercise_migration(root):
    root.mkdir()
    config = {'schema_version': 1, 'harness_version': '0.1', 'project': 'legacy', 'checks': {
        'custom': {'state': 'configured', 'command': [sys.executable, '-c', "print('custom')"],
                   'cwd': '.', 'timeout': 12.5}}}
    (root / 'harness.json').write_text(json.dumps(config), encoding='utf-8')
    memories = {'regras-negocio.md': 'REG-1: Limite aprovado de 300 entregas.',
                'decisoes.md': 'DEC-1: Manter a ordem para integrações futuras.',
                'problemas-conhecidos.md': 'PROB-1: Timeout confirmado no provedor.'}
    (root / 'memoria').mkdir()
    for name, text in memories.items():
        (root / 'memoria' / name).write_text(text, encoding='utf-8')
    report_name = 'planos/relatorios.md'
    report = root / report_name
    report.parent.mkdir()
    report.write_bytes(b'- Validate provider billing before expanding usage.\r\n- Temporary test log.\r\n')
    log = root / '.harness/results/previous.log'
    log.parent.mkdir(parents=True)
    log.write_bytes(b'Preserve evidence.')
    before = snapshot(root)
    preview = invoke(root, ['update', '--dry-run'])
    assert preview['review_required'] == [report_name]
    assert snapshot(root) == before
    assert invoke(root, ['update'], code=3)['status'] == 'review_required'
    assert snapshot(root) == before
    review = {'destinations': preview['destinations'], 'sources': {report_name: {
        'sha256': sha256(report.read_bytes()).hexdigest(), 'archive': True, 'findings': [{
            'category': 'pending', 'text': 'Validate provider billing before expanding usage.', 'line': 1}]}}}
    review_path = root / 'review.json'
    review_path.write_text(json.dumps(review), encoding='utf-8')
    result = invoke(root, ['update', '--migration-review', str(review_path)])
    assert result['status'] == 'complete'
    assert load_config(root)['checks'] == config['checks']
    assert load_config(root)['schema_version'] == 2
    assert not report.exists()
    assert (Path(result['backup']) / report_name).read_bytes() == before[report_name]
    assert log.read_bytes() == before['.harness/results/previous.log']
    for name, text in memories.items():
        assert text in (root / '.harness/memoria' / name).read_text(encoding='utf-8')
    pending = (root / '.harness/pendencias.md').read_text(encoding='utf-8')
    assert 'Validate provider billing before expanding usage.' in pending
    assert 'Temporary test log.' not in pending
    stable = snapshot(root)
    again = update_project(root)
    assert again['status'] == 'complete' and not again['updated'] and again['backup'] is None
    assert snapshot(root) == stable
    assert invoke(root, ['sdd', 'new', '--mode', 'lite', '--title', 'After migration'])['mode'] == 'lite'


exercise_modes(Path(sys.argv[2]).parent / 'sdd-contract')
exercise_migration(Path(sys.argv[2]).parent / 'legacy-contract')
