import contextlib
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from harness.config import ConfigError
from harness.installer import init_project
from harness.project_storage import project_lock
from harness.runner import main
from tests.helpers import directory_link, temporary_project


class FindingTests(unittest.TestCase):
    def setUp(self):
        directory = temporary_project()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / 'maps.py'
        self.source.write_text('def calculateBestDistance():\n    return api(), api(), api()\n', encoding='utf-8')

    def finding(self, **changes):
        return {
            'relevant': True, 'component': 'maps.calculateBestDistance',
            'problem': 'repeated-distance-requests', 'category': 'risco', 'state': 'hipótese',
            'description': 'Possível custo desnecessário em três chamadas à API.',
            'evidence': [{'file': 'maps.py', 'line': 2, 'detail': 'Três chamadas a api() no mesmo retorno.'}],
            'impact': 'Cada execução pode consumir três requisições faturáveis; custo não medido.',
            'action': 'Avaliar com a equipe se uma chamada atende ao contrato.',
            'origin': '007-pendencias', 'persistent': False, **changes,
        }

    def record(self, finding=None, **options):
        from harness.findings import FindingStore
        return FindingStore(self.root).record(finding or self.finding(), **options)

    def pending(self):
        return (self.root / '.harness/pendencias.md').read_text(encoding='utf-8')

    def memory(self):
        return (self.root / '.harness/memoria/problemas-conhecidos.md').read_text(encoding='utf-8')

    def test_cli_records_out_of_scope_cost_without_changing_application(self):
        init_project(self.root)
        before = self.source.read_bytes()
        payload = self.root / 'finding.json'
        payload.write_text(json.dumps(self.finding()), encoding='utf-8')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['sdd', 'finding', '--project', str(self.root), '--input', str(payload)])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result['status'], 'created')
        for text in ('hipótese', 'maps.py:2', 'custo não medido', '007-pendencias', result['id']):
            self.assertIn(text, self.pending())
        self.assertEqual(self.source.read_bytes(), before)
        self.assertNotIn('api()', (self.root / '.harness/memoria/regras-negocio.md').read_text(encoding='utf-8'))

    def test_repeated_run_is_noop_and_keeps_id_when_status_changes(self):
        first = self.record()
        before = (self.root / '.harness/pendencias.md').read_bytes()
        self.assertEqual(self.record()['status'], 'unchanged')
        self.assertEqual((self.root / '.harness/pendencias.md').read_bytes(), before)
        changed = self.finding(component=' maps.calculateBestDistance ', state='confirmado',
                               confirmation='Teste manual reproduziu três chamadas com a mesma entrada.')
        changed['evidence'].append({'file': 'maps.py', 'line': 1, 'detail': 'Função afetada.'})
        second = self.record(changed)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(self.pending().count('## PEN-'), 1)
        self.assertIn('confirmado', self.pending())
        self.assertIn('maps.py:1', self.pending())

    def test_different_problem_in_same_component_is_separate(self):
        self.record()
        self.record(self.finding(problem='missing-timeout', description='Chamada sem limite de espera.'))
        self.assertEqual(self.pending().count('## PEN-'), 2)

    def test_case_sensitive_components_keep_separate_identities(self):
        first = self.record()
        second = self.record(self.finding(component='maps.calculatebestdistance'))
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(self.pending().count('## PEN-'), 2)

    def test_generic_and_transient_findings_leave_no_artifacts(self):
        candidates = [self.finding(relevant=False), self.finding(evidence=[]),
                      self.finding(category='melhoria sugerida', description='Melhorar organização.'),
                      self.finding(impact=''), self.finding(state='confirmado'),
                      self.finding(state='resolvido'), self.finding(state='descartado')]
        for candidate in candidates:
            self.assertEqual(self.record(candidate)['status'], 'ignored')
        self.assertFalse((self.root / '.harness').exists())

    def test_suggestion_requires_specific_benefit_and_tradeoff(self):
        result = self.record(self.finding(category='melhoria sugerida',
                                         benefit='Reduzir até duas chamadas por cálculo.',
                                         tradeoff='Validar se uma resposta cobre os mesmos destinos.'))
        self.assertEqual(result['status'], 'created')
        self.assertIn('Benefício: Reduzir até duas', self.pending())
        self.assertIn('Trade-off: Validar', self.pending())

    def test_persistent_problem_is_described_once_and_status_is_updated(self):
        finding = self.finding(persistent=True, category='problema')
        result = self.record(finding)
        self.assertIn(result['memory_id'], self.pending())
        self.assertNotIn(finding['description'], self.pending())
        self.assertIn(finding['description'], self.memory())
        self.record({**finding, 'state': 'resolvido'})
        self.assertIn('Estado: resolvido', self.memory())
        self.assertIn('Estado: resolvido', self.pending())
        self.assertEqual(self.memory().count('## PROB-'), 1)

    def test_promotion_preserves_evidence_and_origin_without_copying_description(self):
        original = self.finding()
        first = self.record(original)
        result = self.record(self.finding(persistent=True, origin='008-outra-tarefa',
                                          evidence=[{'file': 'maps.py', 'detail': 'Outro caminho afetado.'}]))
        self.assertEqual(result['id'], first['id'])
        self.assertNotIn(original['description'], self.pending())
        self.assertIn('maps.py:2', self.memory())
        self.assertIn('007-pendencias', self.memory())
        self.assertIn('008-outra-tarefa', self.memory())
        self.record(original)
        self.assertNotIn(original['description'], self.pending())

    def test_custom_markdown_is_preserved(self):
        path = self.root / '.harness/pendencias.md'
        path.parent.mkdir()
        path.write_text('# Minhas pendências\n\n- ITEM-1: discutir contrato.\n', encoding='utf-8')
        self.record()
        self.record(self.finding(state='aguardando avaliação'))
        self.assertTrue(self.pending().startswith('# Minhas pendências\n\n- ITEM-1: discutir contrato.\n'))

    def test_invalid_fields_and_unsafe_evidence_are_rejected_without_writes(self):
        for changes in ({'category': 'elogio'}, {'state': 'aprovado'}, {'relevant': 'yes'},
                        {'persistent': 'yes'}, {'description': 'line\n<!-- injection -->'},
                        {'evidence': [{'file': '../outside.py', 'detail': 'Escape.'}]},
                        {'evidence': [{'file': 'absent.py', 'detail': 'Invented.'}]},
                        {'evidence': [{'file': 'maps.py', 'line': 100, 'detail': 'Invented.'}]}):
            with self.subTest(changes=changes), self.assertRaises(ConfigError):
                self.record(self.finding(**changes))
        self.assertFalse((self.root / '.harness').exists())

    def test_off_does_not_create_management_files(self):
        self.assertEqual(self.record(mode='off')['status'], 'ignored')
        self.assertFalse((self.root / '.harness').exists())

    def test_cli_off_override_and_configured_off_do_not_read_input_or_create_documents(self):
        init_project(self.root)
        config_path = self.root / '.harness/harness.json'
        config = json.loads(config_path.read_text(encoding='utf-8'))
        config['sdd']['mode'] = 'off'
        config_path.write_text(json.dumps(config), encoding='utf-8')
        for options in ([], ['--mode', 'off']):
            before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = main(['sdd', 'finding', '--project', str(self.root), '--input', 'absent.json', *options])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())['status'], 'ignored')
            self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_malformed_markers_and_invalid_encoding_preserve_documents(self):
        path = self.root / '.harness/pendencias.md'
        path.parent.mkdir()
        for content in (b'# Preserve\n<!-- harness:finding:broken -->\n', b'\xffpreserve'):
            path.write_bytes(content)
            with self.assertRaises((ConfigError, UnicodeError)):
                self.record()
            self.assertEqual(path.read_bytes(), content)

    def test_crlf_records_do_not_duplicate_evidence_on_update(self):
        self.record()
        path = self.root / '.harness/pendencias.md'
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
        self.record(self.finding(state='observado'))
        self.assertEqual(self.pending().count('- Evidência:'), 1)

    def test_directory_conflict_is_found_before_any_write(self):
        (self.root / '.harness/memoria/problemas-conhecidos.md').mkdir(parents=True)
        before = set(self.root.rglob('*'))
        with self.assertRaises((ConfigError, OSError)):
            self.record(self.finding(persistent=True))
        self.assertEqual(set(self.root.rglob('*')), before)

    def test_links_are_rejected_and_external_files_untouched(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.root / '.harness').mkdir()
        directory_link(self.root / '.harness/memoria', outside)
        with self.assertRaises(ConfigError):
            self.record(self.finding(persistent=True))
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.root / '.harness/pendencias.md').exists())

    def test_tracked_document_is_refused_and_index_preserved(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        init_project(self.root)
        path = '.harness/pendencias.md'
        subprocess.run(['git', '-C', str(self.root), 'add', '-f', path], check=True, capture_output=True)
        index = (self.root / '.git/index').read_bytes()
        before = self.pending()
        with self.assertRaises(ConfigError):
            self.record()
        self.assertEqual(self.pending(), before)
        self.assertEqual((self.root / '.git/index').read_bytes(), index)

    def test_unprotected_git_project_is_refused(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        with self.assertRaises(ConfigError):
            self.record()
        self.assertFalse((self.root / '.harness').exists())

    def test_project_lock_prevents_concurrent_writes(self):
        with project_lock(self.root), self.assertRaises(ConfigError):
            self.record()
        self.assertFalse((self.root / '.harness/pendencias.md').exists())

    def test_interrupted_persistent_write_is_repaired_on_retry(self):
        from harness.project_storage import atomic_write
        def fail_pending(path, data):
            if path.name == 'pendencias.md':
                raise OSError('simulated write failure')
            return atomic_write(path, data)
        with patch('harness.findings.atomic_write', side_effect=fail_pending), self.assertRaises(OSError):
            self.record(self.finding(persistent=True))
        self.record(self.finding(persistent=True))
        self.assertEqual(self.memory().count('## PROB-'), 1)
        self.assertEqual(self.pending().count('## PEN-'), 1)
