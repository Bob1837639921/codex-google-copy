import asyncio
import json
import unittest
from pathlib import Path

from action_executor import UniversalActionExecutor
from agent_core import BrowserAgent
from auto_operator import AutoOperator, AutoOperatorConfig
from scripts import nodex_mcp_server


class EchoWebSocket:
    def __init__(self):
        self.responses = asyncio.Queue()
        self.closed = False
        self.sent = []

    async def send(self, message):
        payload = json.loads(message)
        self.sent.append(payload)
        await self.responses.put(
            json.dumps(
                {
                    "id": payload["id"],
                    "status": "success",
                    "result": payload["action"],
                }
            )
        )

    async def recv(self):
        return await self.responses.get()

    async def close(self):
        self.closed = True


class SilentWebSocket:
    async def send(self, message):
        return None

    async def recv(self):
        await asyncio.sleep(60)

    async def close(self):
        return None


class RiskSnapshotWebSocket(EchoWebSocket):
    async def send(self, message):
        payload = json.loads(message)
        self.sent.append(payload)
        await self.responses.put(
            json.dumps(
                {
                    "id": payload["id"],
                    "status": "success",
                    "blockedByLogin": False,
                    "blockedByRisk": True,
                    "blockerReason": "访问频繁",
                    "dom": [],
                },
                ensure_ascii=False,
            )
        )


class PlanAgent:
    async def connect(self):
        return True

    async def init(self, task_name):
        return {"status": "success"}

    async def navigate(self, url):
        return {"status": "success", "url": url}

    async def snapshot(self):
        return {"blocked_by_login": False, "dom": []}

    async def close(self):
        return None


class LocatorAgent:
    async def evaluate(self, code):
        return {"selector": "button", "count": 2}


class PersistentAgent:
    def __init__(self):
        self.websocket = object()
        self.close_calls = 0

    async def close(self):
        self.websocket = None
        self.close_calls += 1


class BrowserCoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_commands_are_safe_when_called_concurrently(self):
        agent = BrowserAgent(command_timeout=1)
        agent.websocket = EchoWebSocket()

        first, second = await asyncio.gather(
            agent._send_command("first"),
            agent._send_command("second"),
        )

        self.assertEqual(first["result"], "first")
        self.assertEqual(second["result"], "second")

    async def test_command_timeout_is_explicit(self):
        agent = BrowserAgent(command_timeout=0.01)
        agent.websocket = SilentWebSocket()

        with self.assertRaisesRegex(TimeoutError, "timed out"):
            await agent._send_command("never-replies")

    async def test_typing_can_skip_enter_submission(self):
        agent = BrowserAgent(command_timeout=1)
        websocket = EchoWebSocket()
        agent.websocket = websocket

        await agent.type("#query", "NodeX", submit=False)

        self.assertFalse(websocket.sent[0]["submit"])

    async def test_session_id_is_attached_to_every_command(self):
        agent = BrowserAgent(command_timeout=1, session_id="session-a")
        websocket = EchoWebSocket()
        agent.websocket = websocket

        await agent._send_command("snapshot")

        self.assertEqual(websocket.sent[0]["sessionId"], "session-a")

    async def test_unicode_task_name_is_preserved(self):
        agent = BrowserAgent(command_timeout=1, session_id="unicode-session")
        websocket = EchoWebSocket()
        agent.websocket = websocket

        await agent.init("小红书猫粮口碑与京东比价")

        self.assertEqual(websocket.sent[0]["taskName"], "小红书猫粮口碑与京东比价")

    async def test_visibility_defaults_can_be_changed_per_session(self):
        agent = BrowserAgent(command_timeout=1, session_id="background-session")
        websocket = EchoWebSocket()
        agent.websocket = websocket

        await agent.set_visibility(False)

        self.assertEqual(websocket.sent[0]["action"], "setVisibility")
        self.assertEqual(websocket.sent[0]["sessionId"], "background-session")
        self.assertFalse(websocket.sent[0]["visible"])

    async def test_snapshot_preserves_site_risk_blocker(self):
        agent = BrowserAgent(command_timeout=1)
        agent.websocket = RiskSnapshotWebSocket()

        snapshot = await agent.snapshot()

        self.assertTrue(snapshot["blocked_by_risk"])
        self.assertEqual(snapshot["blocker_reason"], "访问频繁")

    async def test_mcp_direct_tools_reuse_shared_bridge_connection(self):
        previous = nodex_mcp_server._shared_agent
        agent = PersistentAgent()
        nodex_mcp_server._shared_agent = agent
        try:
            first = await nodex_mcp_server.with_agent(lambda current: asyncio.sleep(0, result=current))
            second = await nodex_mcp_server.with_agent(lambda current: asyncio.sleep(0, result=current))
        finally:
            nodex_mcp_server._shared_agent = previous

        self.assertIs(first, agent)
        self.assertIs(second, agent)
        self.assertEqual(agent.close_calls, 0)

    async def test_close_tab_uses_exact_tab_id(self):
        agent = BrowserAgent(command_timeout=1, session_id="cleanup-session")
        websocket = EchoWebSocket()
        agent.websocket = websocket

        await agent.close_tab(42)

        self.assertEqual(websocket.sent[0]["action"], "closeTab")
        self.assertEqual(websocket.sent[0]["tabId"], 42)

    async def test_ambiguous_locator_is_rejected(self):
        executor = UniversalActionExecutor(LocatorAgent())

        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            await executor.resolve_selector({"text": "Save"}, timeout=0.01)

    async def test_action_plan_reports_post_action_evidence(self):
        executor = UniversalActionExecutor(PlanAgent())
        result = await executor.run_plan_data(
            {
                "group_name": "test",
                "steps": [
                    {"action": "navigate", "url": "https://example.com"},
                    {"action": "snapshot"},
                ],
            }
        )

        self.assertEqual(result["verification"]["status"], "present")
        self.assertEqual(result["verification"]["completion_claim"], "review_evidence")


class ConfigurationTests(unittest.TestCase):
    def test_extension_uses_dynamic_stability_without_fixed_rate_limits(self):
        source = (Path(__file__).parents[1] / "extension" / "background.js").read_text(encoding="utf-8")

        self.assertIn("waitForPageStability", source)
        self.assertNotIn("maxActionsPerWindow", source)
        self.assertNotIn("minIntervalMs", source)

    def test_stdio_is_configured_for_utf8(self):
        class Stream:
            def __init__(self):
                self.configuration = None

            def reconfigure(self, **kwargs):
                self.configuration = kwargs

        stream = Stream()
        nodex_mcp_server.configure_stdio_utf8(stream)

        self.assertEqual(stream.configuration, {"encoding": "utf-8", "errors": "strict"})

    def test_empty_extraction_is_not_meaningful(self):
        self.assertFalse(AutoOperator.has_meaningful_result([]))
        self.assertFalse(AutoOperator.has_meaningful_result({}))
        self.assertTrue(AutoOperator.has_meaningful_result([{"title": "result"}]))

    def test_site_profile_does_not_claim_empty_results(self):
        operator = AutoOperator(AutoOperatorConfig(goal="search NodeX", persist_report=False))
        operator.profiles = [
            {
                "name": "example",
                "domains": ["example.com"],
                "extract_results_js": "[]",
            }
        ]
        operator._profile_search_loaded = True
        operator._profile_extract_attempts = 2
        operator._profile_extraction_result = []

        action = operator.plan_next(
            {"visual_snapshot": {"viewport": {"url": "https://example.com/search"}}}
        )

        self.assertEqual(action["action"], "stop")
        self.assertEqual(action["status"], "needs_planner")

    def test_auto_operator_stops_on_site_risk_warning(self):
        operator = AutoOperator(AutoOperatorConfig(goal="search wet food", persist_report=False))

        blocker = operator.detect_blocker(
            {
                "snapshot": {
                    "blocked_by_login": False,
                    "blocked_by_risk": True,
                    "blocker_reason": "访问频繁",
                }
            }
        )

        self.assertIn("访问频繁", blocker)

    def test_mcp_mutations_reject_site_risk_warning(self):
        with self.assertRaisesRegex(RuntimeError, "访问频繁"):
            nodex_mcp_server.ensure_snapshot_allows_interaction(
                {
                    "blocked_by_login": False,
                    "blocked_by_risk": True,
                    "blocker_reason": "访问频繁",
                }
            )

    def test_mcp_surface_contains_only_generic_browser_tools(self):
        names = {definition["name"] for definition in nodex_mcp_server.TOOL_DEFINITIONS}

        self.assertEqual(names, set(nodex_mcp_server.TOOLS))
        self.assertIn("nodex_observe", names)
        self.assertIn("nodex_claim_tab", names)
        self.assertNotIn("nodex_generate_character", names)
        self.assertNotIn("nodex_xhs_search", names)


if __name__ == "__main__":
    unittest.main()
