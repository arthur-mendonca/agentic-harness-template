from pathlib import Path
import unittest

from harness.config import ConfigError
from harness.installer import init_project
from harness.project import PROJECT_FILES
from tests.helpers import temporary_project, directory_link


MEMORY = ('regras-negocio.md', 'problemas-conhecidos.md', 'decisoes.md')


class MemoryTests(unittest.TestCase):
    def test_creation_preservation_and_differences(self):
        with temporary_project() as directory:
            root = Path(directory)
            summary = init_project(root)
            self.assertIn('.harness/memoria/', summary['created'])
            for name in MEMORY:
                relative = '.harness/memoria/' + name
                self.assertEqual((root / relative).read_text(encoding='utf-8'), PROJECT_FILES[relative])
                (root / relative).write_text('Registro confirmado: preservar\n', encoding='utf-8')
            summary = init_project(root)
            self.assertEqual(summary['created'], [])
            for name in MEMORY:
                relative = '.harness/memoria/' + name
                self.assertIn(relative, summary['differences'])
                self.assertEqual((root / relative).read_text(encoding='utf-8'), 'Registro confirmado: preservar\n')

    def test_conflicts_prevent_all_writes(self):
        for relative in ('.harness/memoria', *('.harness/memoria/' + name for name in MEMORY)):
            with self.subTest(relative=relative), temporary_project() as directory:
                root = Path(directory)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative == '.harness/memoria':
                    path.write_text('preservar', encoding='utf-8')
                else:
                    path.mkdir()
                before = set(root.rglob('*'))
                with self.assertRaises(ConfigError):
                    init_project(root)
                self.assertEqual(set(root.rglob('*')), before)

    def test_external_memory_link_prevents_partial_install(self):
        with temporary_project() as directory:
            root = Path(directory)
            project, outside = root / 'project', root / 'outside'
            project.mkdir()
            outside.mkdir()
            (project / '.harness').mkdir()
            directory_link(project / '.harness/memoria', outside)
            with self.assertRaises(ConfigError):
                init_project(project)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertFalse((project / 'AGENTS.md').exists())

    def test_instruction_contract(self):
        agents = PROJECT_FILES['AGENTS.md']
        skill = (Path(__file__).resolve().parents[1] / 'skills/verified-development/SKILL.md').read_text(encoding='utf-8')
        for text in (agents, skill):
            self.assertIn('.harness/results/', text)
            self.assertNotIn('acrescente uma entrada real da tarefa', text)
            self.assertNotIn('uma entrada por tarefa', text)
        self.assertTrue(agents.startswith('# AGENTS.md — Regras permanentes\n'))
        self.assertIn('Consulte seletivamente regras, decisões e problemas relevantes', agents)
        self.assertIn('somente se a omissão prejudicar trabalho futuro', agents)
        self.assertIn('recuperação seletiva', skill)
        self.assertIn('A ausência deste registro', skill)
        self.assertIn('Não criar uma entrada', PROJECT_FILES['.harness/planos/relatorios.md'])
        self.assertIn('ação futura concreta', PROJECT_FILES['.harness/planos/pendencias.md'])
