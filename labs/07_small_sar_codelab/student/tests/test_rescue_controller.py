"""Readable standard-library checks for the three Flood Rescue Controller TODOs.

Run this file through ``python workshop.py test 1`` (or 2, 3, or all).  The
tests deliberately use Python's built-in ``unittest`` module so students do not
need to install a test package on their own laptops.
"""

from __future__ import annotations

import argparse
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

STUDENT_ROOT = Path(__file__).resolve().parents[1]
if str(STUDENT_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDENT_ROOT))

from _support import runtime
from _support.types import ReasonCode, RescueDecision, RescueEventType, TraceDecision
from exercise import rescue_controller


class RescueControllerTests(unittest.TestCase):
    """One focused group of checks for each student function."""

    cases: ClassVar[dict[str, runtime.PublicCase]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = runtime.build_cases()

    def test_todo_1_eligible_resources_filters_and_sorts(self) -> None:
        case = self.cases["allocation"]
        first = case.resources[0]
        slower = replace(first, resource_id="RES-SLOWER", routed_travel_s=first.routed_travel_s + 100)
        wrong_route = replace(first, resource_id="RES-WRONG-ROUTE", route_id="XNG-03")
        unreachable = replace(first, resource_id="RES-UNREACHABLE", route_reachable=False)
        unavailable = replace(first, resource_id="RES-BUSY", currently_available=False)

        selected = rescue_controller.eligible_resources(
            case.request,
            (slower, wrong_route, unreachable, unavailable, first),
        )

        self.assertEqual([item.resource_id for item in selected], ["RES-ENGINE-01", "RES-SLOWER"])

    def test_todo_2_clear_plus_capacity_allocates(self) -> None:
        case = self.cases["allocation"]

        decision = rescue_controller.decide_rescue(case.request, case.authorization, case.resources)

        self.assertIs(decision.event_type, RescueEventType.ALLOCATION)
        self.assertIs(decision.reason_code, ReasonCode.ALLOCATED_COMPATIBLE_CAPACITY)
        self.assertEqual(decision.selected_resource_id, "RES-ENGINE-01")
        self.assertEqual(decision.call_id, case.authorization.call_id)
        self.assertEqual(decision.trace_record_id, case.authorization.record_id)

    def test_todo_2_hold_refuses_even_when_capacity_exists(self) -> None:
        case = self.cases["evidence_hold"]
        self.assertTrue(any(resource.currently_available for resource in case.resources))

        decision = rescue_controller.decide_rescue(case.request, case.authorization, case.resources)

        self.assertIs(decision.trace_decision, TraceDecision.HOLD)
        self.assertIs(decision.event_type, RescueEventType.REFUSAL)
        self.assertIs(decision.reason_code, ReasonCode.TRACE_NOT_CLEAR)
        self.assertIsNone(decision.selected_resource_id)

    def test_todo_2_clear_without_capacity_refuses(self) -> None:
        case = self.cases["capacity_refusal"]
        self.assertIs(case.authorization.decision, TraceDecision.CLEAR)
        self.assertFalse(any(resource.currently_available for resource in case.resources))

        decision = rescue_controller.decide_rescue(case.request, case.authorization, case.resources)

        self.assertIs(decision.event_type, RescueEventType.REFUSAL)
        self.assertIs(decision.reason_code, ReasonCode.NO_COMPATIBLE_CAPACITY)
        self.assertIsNone(decision.selected_resource_id)

    def test_todo_2_rejects_a_mismatched_call(self) -> None:
        case = self.cases["allocation"]
        mismatched = replace(case.authorization, call_id="C8-not-the-request")

        with self.assertRaises(ValueError):
            rescue_controller.decide_rescue(case.request, mismatched, case.resources)

    def test_todo_2_rejects_a_mismatched_situation(self) -> None:
        case = self.cases["allocation"]
        mismatched = replace(case.authorization, belief_cluster_id="BC-not-the-request")

        with self.assertRaises(ValueError):
            rescue_controller.decide_rescue(case.request, mismatched, case.resources)

    def _initial_allocation(self) -> RescueDecision:
        allocation = self.cases["allocation"]
        return rescue_controller.decide_rescue(
            allocation.request,
            allocation.authorization,
            allocation.resources,
        )

    def test_todo_3_visible_repair_appends_and_preserves_allocation(self) -> None:
        repair = self.cases["visible_repair"]
        initial = self._initial_allocation()

        history = rescue_controller.apply_visible_repair((initial,), repair.authorization)

        self.assertIs(history[0], initial)
        self.assertEqual(len(history), 2)
        self.assertIs(history[1].event_type, RescueEventType.REPAIR)
        self.assertIs(history[1].reason_code, ReasonCode.VISIBLE_EVIDENCE_REPAIR)
        self.assertIsNone(history[1].selected_resource_id)
        self.assertGreater(history[1].trace_record_version, history[0].trace_record_version)

    def test_todo_3_requires_visible_basis(self) -> None:
        repair = self.cases["visible_repair"]
        unsupported = replace(repair.authorization, visible_evidence_basis=())

        with self.assertRaises(ValueError):
            rescue_controller.apply_visible_repair((self._initial_allocation(),), unsupported)

    def test_todo_3_rejects_empty_history(self) -> None:
        repair = self.cases["visible_repair"]

        with self.assertRaises(ValueError):
            rescue_controller.apply_visible_repair((), repair.authorization)

    def test_todo_3_rejects_a_different_situation(self) -> None:
        repair = self.cases["visible_repair"]
        wrong_situation = replace(repair.authorization, belief_cluster_id="BC-different")

        with self.assertRaises(ValueError):
            rescue_controller.apply_visible_repair((self._initial_allocation(),), wrong_situation)

    def test_todo_3_rejects_a_different_trace_record(self) -> None:
        repair = self.cases["visible_repair"]
        wrong_record = replace(repair.authorization, record_id="TR-different")

        with self.assertRaises(ValueError):
            rescue_controller.apply_visible_repair((self._initial_allocation(),), wrong_record)

    def test_todo_3_requires_a_later_version(self) -> None:
        repair = self.cases["visible_repair"]
        old_version = replace(
            repair.authorization,
            record_version=self._initial_allocation().trace_record_version,
        )

        with self.assertRaises(ValueError):
            rescue_controller.apply_visible_repair((self._initial_allocation(),), old_version)


TODO_TESTS = {
    "1": ("test_todo_1_eligible_resources_filters_and_sorts",),
    "2": (
        "test_todo_2_clear_plus_capacity_allocates",
        "test_todo_2_hold_refuses_even_when_capacity_exists",
        "test_todo_2_clear_without_capacity_refuses",
        "test_todo_2_rejects_a_mismatched_call",
        "test_todo_2_rejects_a_mismatched_situation",
    ),
    "3": (
        "test_todo_3_visible_repair_appends_and_preserves_allocation",
        "test_todo_3_requires_visible_basis",
        "test_todo_3_rejects_empty_history",
        "test_todo_3_rejects_a_different_situation",
        "test_todo_3_rejects_a_different_trace_record",
        "test_todo_3_requires_a_later_version",
    ),
}


def selected_suite(todo: str) -> unittest.TestSuite:
    """Return exactly the focused tests requested by the workshop command."""

    if todo == "all":
        names = tuple(name for group in TODO_TESTS.values() for name in group)
    else:
        names = TODO_TESTS[todo]
    return unittest.TestSuite(RescueControllerTests(name) for name in names)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--todo", choices=("1", "2", "3", "all"), default="all")
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(selected_suite(args.todo))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
