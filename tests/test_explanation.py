"""Ground truth for behavioral explanation evals; these tests do not grade prose."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, call

from harness.installer import install_skills
from tests.helpers import temporary_project

FIXTURES = Path(__file__).parent / 'fixtures' / 'explanation'


def load_example(name):
    spec = importlib.util.spec_from_file_location('explanation_' + name, FIXTURES / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.calculateBestDistance


class ExplanationScenarioTests(unittest.TestCase):
    def test_previous_version_queries_only_driving_even_when_opted_in(self):
        client = Mock()
        client.distance_matrix.return_value = 12
        self.assertEqual(load_example('before')(client, 'A', 'B', compare_modes=True), 12)
        client.distance_matrix.assert_called_once_with('A', 'B', mode='driving')

    def test_default_still_queries_only_driving(self):
        client = Mock()
        client.distance_matrix.return_value = 12
        self.assertEqual(load_example('after')(client, 'A', 'B'), 12)
        client.distance_matrix.assert_called_once_with('A', 'B', mode='driving')

    def test_opt_in_queries_three_modes_sequentially_and_selects_minimum(self):
        client = Mock()
        client.distance_matrix.side_effect = [12, 9, 10]
        self.assertEqual(load_example('after')(client, 'A', 'B', compare_modes=True), 9)
        self.assertEqual(client.distance_matrix.call_args_list, [
            call('A', 'B', mode='driving'), call('A', 'B', mode='walking'),
            call('A', 'B', mode='bicycling'),
        ])

    def test_no_cache_and_no_function_retry_amplify_only_successful_comparisons(self):
        client = Mock()
        client.distance_matrix.return_value = 12
        calculate = load_example('after')
        for _ in range(4):
            calculate(client, 'A', 'B', compare_modes=True)
        self.assertEqual(client.distance_matrix.call_count, 12)
        for failing_call in (1, 2, 3):
            with self.subTest(failing_call=failing_call):
                client.reset_mock()
                client.distance_matrix.side_effect = [12] * (failing_call - 1) + [RuntimeError('provider failed')]
                with self.assertRaisesRegex(RuntimeError, 'provider failed'):
                    calculate(client, 'A', 'B', compare_modes=True)
                self.assertEqual(client.distance_matrix.call_count, failing_call)

    def test_eval_can_use_only_the_installed_skill_without_checkout_resources(self):
        with temporary_project() as directory:
            destination = Path(directory) / 'skills'
            install_skills(destination)
            installed = destination / 'verified-development/SKILL.md'
            source = Path(__file__).resolve().parents[1] / 'skills/verified-development/SKILL.md'
            self.assertEqual(installed.read_text(encoding='utf-8'), source.read_text(encoding='utf-8'))
            self.assertEqual({path.name for path in installed.parent.iterdir()}, {'SKILL.md'})
