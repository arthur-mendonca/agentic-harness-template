"""Ground truth for behavioral explanation evals; these tests do not grade prose."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, call

from harness.installer import install_skills
from tests.helpers import temporary_project

FIXTURES = Path(__file__).parent / 'fixtures' / 'explanation'


def load_example(name, function='calculateBestDistance'):
    spec = importlib.util.spec_from_file_location('explanation_' + name, FIXTURES / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function)


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


class SQLExplanationScenarioTests(unittest.TestCase):
    def setUp(self):
        self.orders = [{'id': 3, 'customer_id': 7}, {'id': 1, 'customer_id': 7}, {'id': 2, 'customer_id': 8}]
        self.customers = {7: {'id': 7, 'email': 'a@example.test'}, 8: {'id': 8, 'email': 'b@example.test'}}
        self.db = Mock()
        self.db.fetch_orders.return_value = self.orders
        self.db.fetch_customer.side_effect = self.customers.__getitem__
        self.db.fetch_customers.return_value = list(self.customers.values())

    def test_batch_replaces_n_plus_one_and_preserves_order_and_duplicate_customers(self):
        expected = [(3, 'a@example.test'), (1, 'a@example.test'), (2, 'b@example.test')]
        before = load_example('sql_before', 'load_order_emails')
        after = load_example('sql_after', 'load_order_emails')
        self.assertEqual(before(self.db, [3, 1, 2]), expected)
        self.assertEqual(self.db.mock_calls, [call.fetch_orders([3, 1, 2]), call.fetch_customer(7),
                                             call.fetch_customer(7), call.fetch_customer(8)])
        self.db.reset_mock()
        self.assertEqual(after(self.db, [3, 1, 2]), expected)
        self.assertEqual(self.db.mock_calls, [call.fetch_orders([3, 1, 2]), call.fetch_customers([7, 8])])

    def test_empty_result_makes_only_the_order_query(self):
        self.db.fetch_orders.return_value = []
        self.assertEqual(load_example('sql_after', 'load_order_emails')(self.db, []), [])
        self.assertEqual(self.db.mock_calls, [call.fetch_orders([])])

    def test_missing_customer_still_propagates_an_error(self):
        self.db.fetch_customers.return_value = [self.customers[7]]
        with self.assertRaises(KeyError):
            load_example('sql_after', 'load_order_emails')(self.db, [3, 1, 2])
        self.assertEqual(self.db.mock_calls, [call.fetch_orders([3, 1, 2]), call.fetch_customers([7, 8])])


class CacheExplanationScenarioTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.store.fetch_profile.return_value = {'name': 'original'}
        self.service = load_example('cache_after', 'ProfileService')(self.store)

    def test_repeated_read_is_cached_and_flat_returned_dict_is_not_shared(self):
        before = load_example('cache_before', 'ProfileService')(self.store)
        before.read_profile('tenant-a', 7)
        before.read_profile('tenant-a', 7)
        self.assertEqual(self.store.fetch_profile.call_count, 2)
        self.store.reset_mock()
        first = self.service.read_profile('tenant-a', 7)
        first['name'] = 'caller edit'
        self.assertEqual(self.service.read_profile('tenant-a', 7), {'name': 'original'})
        self.store.fetch_profile.assert_called_once_with('tenant-a', 7)

    def test_tenants_with_the_same_user_id_have_separate_entries(self):
        self.store.fetch_profile.side_effect = [{'name': 'a'}, {'name': 'b'}]
        self.assertEqual(self.service.read_profile('tenant-a', 7), {'name': 'a'})
        self.assertEqual(self.service.read_profile('tenant-b', 7), {'name': 'b'})
        self.assertEqual(self.service.read_profile('tenant-a', 7), {'name': 'a'})
        self.assertEqual(self.store.fetch_profile.call_count, 2)

    def test_successful_update_invalidates_only_the_affected_key(self):
        self.service.read_profile('tenant-a', 7)
        self.service.read_profile('tenant-b', 7)
        self.service.update_profile('tenant-a', 7, {'name': 'changed'})
        self.store.fetch_profile.return_value = {'name': 'changed'}
        self.assertEqual(self.service.read_profile('tenant-a', 7), {'name': 'changed'})
        self.assertEqual(self.service.read_profile('tenant-b', 7), {'name': 'original'})
        self.assertEqual(self.store.fetch_profile.call_count, 3)
        self.store.update_profile.assert_called_once_with('tenant-a', 7, {'name': 'changed'})

    def test_failed_update_propagates_and_keeps_the_cached_value(self):
        self.service.read_profile('tenant-a', 7)
        self.store.update_profile.side_effect = RuntimeError('write failed')
        with self.assertRaisesRegex(RuntimeError, 'write failed'):
            self.service.update_profile('tenant-a', 7, {'name': 'changed'})
        self.assertEqual(self.service.read_profile('tenant-a', 7), {'name': 'original'})
        self.assertEqual(self.store.fetch_profile.call_count, 1)

    def test_external_update_stays_stale_and_instances_do_not_share_cache(self):
        self.service.read_profile('tenant-a', 7)
        self.store.fetch_profile.return_value = {'name': 'external change'}
        self.assertEqual(self.service.read_profile('tenant-a', 7), {'name': 'original'})
        other = load_example('cache_after', 'ProfileService')(self.store)
        self.assertEqual(other.read_profile('tenant-a', 7), {'name': 'external change'})
        self.assertEqual(self.store.fetch_profile.call_count, 2)
