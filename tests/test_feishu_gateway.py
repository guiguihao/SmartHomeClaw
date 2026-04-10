import builtins
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

# Import the functions/variables we need from the Feishu gateway module
from services.feishu.main import handle_message, sent_message_ids, FeishuAppClient

# Helper to create a dummy Feishu client with minimal interface required for the test
class DummyLarkClient:
    class ImV1:
        class Message:
            class Create:
                def __init__(self, success=True, message_id="dummy_msg_id"):
                    self._success = success
                    self.data = SimpleNamespace(message_id=message_id)
                    self.msg = "OK" if success else "FAIL"
                    self.code = 0 if success else 1

                def success(self):
                    return self._success

        def __init__(self):
            self.im = SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(reaction=SimpleNamespace())))

        # The gateway calls client.im.v1.message.create(req)
        # We'll provide a simple stub that returns a response object with .success() and .data.message_id
        @property
        def im(self):
            return SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(reaction=SimpleNamespace())) )

# We'll mock the Lark client builder to return our DummyLarkClient instance
def dummy_lark_client_builder(*args, **kwargs):
    return DummyLarkClient()

# Mock response object for requests.post
class DummyResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._json

@pytest.fixture(autouse=True)
def reset_sent_ids():
    """Ensure sent_message_ids is empty before each test."""
    sent_message_ids.clear()
    yield
    sent_message_ids.clear()

def test_handle_message_success(monkeypatch):
    # Suppress reaction calls (they require a deeper Lark client)
    monkeypatch.setattr('services.feishu.main.add_reaction', lambda *args, **kwargs: None)
    # Prepare a mock FeishuAppClient – its .client attribute will be the dummy Lark client
    dummy_client = SimpleNamespace()
    # Define a minimal response object for Lark's message.create call
    class DummyMessageCreateResponse:
        def __init__(self, message_id="reply123"):
            self._success = True
            self.data = SimpleNamespace(message_id=message_id)
            self.msg = "OK"
            self.code = 0
        def success(self):
            return self._success
    dummy_client.im = SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(create=lambda req: DummyMessageCreateResponse()),
                                                                                                  reaction=SimpleNamespace()))
    app_client = FeishuAppClient(name="bot_test", app_id="id", app_secret="secret")
    app_client.client = dummy_client

    # Patch requests.post to return a fake Agent API reply
    fake_agent_reply = {"response": "Mocked agent answer"}
    def fake_requests_post(url, json, timeout):
        assert url == "http://127.0.0.1:8000/v1/chat"
        # Verify payload content
        assert json["session_id"] == f"{app_client.name}:user123"
        assert json["message"] == "test message"
        return DummyResponse(fake_agent_reply)

    monkeypatch.setattr("services.feishu.main.requests.post", fake_requests_post)

    # Call handle_message – it should add the reply message id to sent_message_ids
    handle_message(app_client, sender_id="user123", msg_id="orig_msg_1", text="test message")

    # After handling, the dummy client should have recorded the reply id "reply123"
    assert "reply123" in sent_message_ids

def test_handle_message_failure(monkeypatch, caplog):
    # Suppress reaction calls as they require full Lark client
    monkeypatch.setattr('services.feishu.main.add_reaction', lambda *args, **kwargs: None)
    # Create a FeishuAppClient with a client that will raise when sending a message
    dummy_client = SimpleNamespace()
    # Simulate a failed Lark message send (success() returns False)
    class DummyMessageCreateFailResponse:
        def __init__(self):
            self._success = False
            self.data = SimpleNamespace()
            self.msg = "FAIL"
            self.code = 1
        def success(self):
            return self._success
    dummy_client.im = SimpleNamespace(v1=SimpleNamespace(message=SimpleNamespace(create=lambda req: DummyMessageCreateFailResponse()),
                                                                                                   reaction=SimpleNamespace()))
    app_client = FeishuAppClient(name="bot_test", app_id="id", app_secret="secret")
    app_client.client = dummy_client

    # Mock requests.post to raise an HTTP error
    def failing_post(*args, **kwargs):
        raise Exception("Network error")
    monkeypatch.setattr("services.feishu.main.requests.post", failing_post)

    # Run handle_message – it should log an error and not add any ids to sent_message_ids
    handle_message(app_client, sender_id="user123", msg_id="orig_msg_2", text="fail test")
    assert len(sent_message_ids) == 0
    # Verify that an error was logged (contains the app name)
    error_logs = [record.message for record in caplog.records if record.levelname == "ERROR"]
    assert any("bot_test" in msg for msg in error_logs)
