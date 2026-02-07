from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("TRIAGE_DB_PATH", str(tmp_path / "api_test.db"))
    monkeypatch.setenv("TRIAGE_REASONER_MODE", "heuristic")
    monkeypatch.setenv("TRIAGE_NOTIFICATIONS_ENABLED", "false")
    monkeypatch.setenv("TRIAGE_AUTH_FORCE_CHANGE_DEFAULTS", "true")
    app = create_app()
    return TestClient(app)


def _login(client: TestClient, *, username: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()


def _complete_first_login(
    client: TestClient,
    *,
    username: str,
    password: str,
) -> dict[str, str]:
    login = _login(client, username=username, password=password)
    token = login["access_token"]
    refresh_token = login["refresh_token"]
    user = login["user"]

    if user["password_change_required"]:
        changed = client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": password,
                "new_password": f"{password}_new1",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert changed.status_code == 200
        token = changed.json()["access_token"]
        refresh_token = changed.json()["refresh_token"]
        user = changed.json()["user"]

    if not user["onboarding_completed"]:
        onboarded = client.post(
            "/api/v1/auth/onboarding-complete",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert onboarded.status_code == 200
        assert onboarded.json()["onboarding_completed"] is True

    return {
        "authorization": f"Bearer {token}",
        "refresh_token": refresh_token,
    }


def test_health_endpoint(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["service"] == "healthcare-triage-api"


def test_password_change_required_is_enforced(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        login = _login(client, username="ops", password="ops123")
        assert login["user"]["password_change_required"] is True
        assert login["user"]["onboarding_completed"] is False

        blocked = client.get(
            "/api/v1/dashboard/metrics",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert blocked.status_code == 403
        assert "Password change is required" in blocked.json()["detail"]

        changed = client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "ops123",
                "new_password": "ops123_new1",
            },
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert changed.status_code == 200
        assert changed.json()["user"]["password_change_required"] is False
        assert changed.json()["user"]["onboarding_completed"] is False

        blocked_for_onboarding = client.get(
            "/api/v1/dashboard/metrics",
            headers={"Authorization": f"Bearer {changed.json()['access_token']}"},
        )
        assert blocked_for_onboarding.status_code == 403
        assert "Onboarding is required" in blocked_for_onboarding.json()["detail"]

        onboarded = client.post(
            "/api/v1/auth/onboarding-complete",
            headers={"Authorization": f"Bearer {changed.json()['access_token']}"},
        )
        assert onboarded.status_code == 200
        assert onboarded.json()["onboarding_completed"] is True

        metrics = client.get(
            "/api/v1/dashboard/metrics",
            headers={"Authorization": f"Bearer {changed.json()['access_token']}"},
        )
        assert metrics.status_code == 200


def test_admin_can_reset_onboarding(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        admin_session = _complete_first_login(client, username="admin", password="admin123")
        ops_session = _complete_first_login(client, username="ops", password="ops123")
        admin_headers = {"Authorization": admin_session["authorization"]}
        ops_headers = {"Authorization": ops_session["authorization"]}

        reset = client.post(
            "/api/v1/auth/onboarding-reset",
            json={"username": "ops"},
            headers=admin_headers,
        )
        assert reset.status_code == 200
        assert reset.json()["username"] == "ops"
        assert reset.json()["onboarding_completed"] is False

        blocked = client.get("/api/v1/dashboard/metrics", headers=ops_headers)
        assert blocked.status_code == 403
        assert "Onboarding is required" in blocked.json()["detail"]

        forbidden = client.post(
            "/api/v1/auth/onboarding-reset",
            json={"username": "nurse"},
            headers=ops_headers,
        )
        assert forbidden.status_code == 403


def test_refresh_token_rotation_and_reuse_detection(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        session = _complete_first_login(client, username="admin", password="admin123")
        first_refresh = session["refresh_token"]

        rotated = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first_refresh},
        )
        assert rotated.status_code == 200
        second_refresh = rotated.json()["refresh_token"]

        reused = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first_refresh},
        )
        assert reused.status_code == 401

        still_valid = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": second_refresh},
        )
        assert still_valid.status_code == 401


def test_intake_and_dashboard_flow(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        session = _complete_first_login(client, username="ops", password="ops123")
        headers = {"Authorization": session["authorization"]}
        intake = client.post(
            "/api/v1/triage/intake",
            json={
                "phone": "5551234567",
                "age": 30,
                "sex": "Female",
                "symptoms": "Cough and cold for two days",
                "auto_book_high_urgency": True,
                "always_route_when_model_requests_human": True,
            },
            headers=headers,
        )
        assert intake.status_code == 200
        body = intake.json()
        assert body["triage_result"]["urgency"] in {"SOON", "ROUTINE", "URGENT", "EMERGENCY"}
        assert body["routing_decision"]["action"] in {"AUTO_BOOK", "QUEUE_REVIEW", "ESCALATE"}

        metrics = client.get("/api/v1/dashboard/metrics", headers=headers)
        assert metrics.status_code == 200
        metric_body = metrics.json()
        assert metric_body["total_slots"] > 0
        assert metric_body["available_slots"] >= 0
        assert metric_body["booked_slots"] == (
            metric_body["total_slots"] - metric_body["available_slots"]
        )
        assert 0 <= metric_body["slot_utilization_percent"] <= 100
        assert metric_body["pending_high_priority_queue"] >= 0
        assert metric_body["total_appointments"] >= 0
        assert metric_body["auto_booked_appointments"] >= 0
        assert metric_body["preempted_appointments"] >= 0
        assert metric_body["triage_events_24h"] >= 1
        assert metric_body["urgent_cases_24h"] >= 0
        assert 0 <= metric_body["avg_confidence_24h"] <= 1


def test_role_restrictions_and_audit_scope(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        ops_session = _complete_first_login(client, username="ops", password="ops123")
        nurse_session = _complete_first_login(client, username="nurse", password="nurse123")
        ops_headers = {"Authorization": ops_session["authorization"]}
        nurse_headers = {"Authorization": nurse_session["authorization"]}

        queue_for_ops = client.get("/api/v1/queue", headers=ops_headers)
        assert queue_for_ops.status_code == 403

        queue_for_nurse = client.get("/api/v1/queue", headers=nurse_headers)
        assert queue_for_nurse.status_code == 200

        audit_for_ops = client.get("/api/v1/audit", headers=ops_headers)
        assert audit_for_ops.status_code == 200
        assert audit_for_ops.json()["role"] == "operations"


def test_dashboard_appointments_phone_scope_by_role(tmp_path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        ops_session = _complete_first_login(client, username="ops", password="ops123")
        admin_session = _complete_first_login(client, username="admin", password="admin123")
        nurse_session = _complete_first_login(client, username="nurse", password="nurse123")
        ops_headers = {"Authorization": ops_session["authorization"]}
        admin_headers = {"Authorization": admin_session["authorization"]}
        nurse_headers = {"Authorization": nurse_session["authorization"]}

        intake = client.post(
            "/api/v1/triage/intake",
            json={
                "phone": "5551234567",
                "age": 31,
                "sex": "Female",
                "symptoms": "cold and fatigue for two days",
                "auto_book_high_urgency": True,
                "always_route_when_model_requests_human": True,
            },
            headers=ops_headers,
        )
        assert intake.status_code == 200

        ops_dashboard = client.get("/api/v1/dashboard/appointments", headers=ops_headers)
        admin_dashboard = client.get("/api/v1/dashboard/appointments", headers=admin_headers)
        nurse_dashboard = client.get("/api/v1/dashboard/appointments", headers=nurse_headers)

        assert ops_dashboard.status_code == 200
        assert admin_dashboard.status_code == 200
        assert nurse_dashboard.status_code == 200

        ops_items = ops_dashboard.json()["items"]
        admin_items = admin_dashboard.json()["items"]
        nurse_items = nurse_dashboard.json()["items"]
        assert admin_items
        assert ops_items
        assert nurse_items

        assert admin_items[0]["phone"] == "5551234567"
        assert nurse_items[0]["phone"] == "***-***-4567"
        assert ops_items[0]["phone"] == "-"


def test_login_rate_limit_and_lockout(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRIAGE_AUTH_LOGIN_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("TRIAGE_AUTH_LOGIN_WINDOW_SECONDS", "300")
    monkeypatch.setenv("TRIAGE_AUTH_LOGIN_LOCKOUT_SECONDS", "900")
    monkeypatch.setenv("TRIAGE_AUTH_TRUST_X_FORWARDED_FOR", "true")

    with _client(tmp_path, monkeypatch) as client:
        for _ in range(2):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "ops", "password": "wrong-password"},
                headers={"x-forwarded-for": "10.10.10.10"},
            )
            assert response.status_code == 401

        locked = client.post(
            "/api/v1/auth/login",
            json={"username": "ops", "password": "wrong-password"},
            headers={"x-forwarded-for": "10.10.10.10"},
        )
        assert locked.status_code == 429
        assert "Retry-After" in locked.headers

        still_locked = client.post(
            "/api/v1/auth/login",
            json={"username": "ops", "password": "ops123"},
            headers={"x-forwarded-for": "10.10.10.10"},
        )
        assert still_locked.status_code == 429

        other_ip_allowed = client.post(
            "/api/v1/auth/login",
            json={"username": "ops", "password": "ops123"},
            headers={"x-forwarded-for": "10.10.10.11"},
        )
        assert other_ip_allowed.status_code == 200


def test_login_ignores_x_forwarded_for_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRIAGE_AUTH_LOGIN_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("TRIAGE_AUTH_LOGIN_WINDOW_SECONDS", "300")
    monkeypatch.setenv("TRIAGE_AUTH_LOGIN_LOCKOUT_SECONDS", "900")
    monkeypatch.delenv("TRIAGE_AUTH_TRUST_X_FORWARDED_FOR", raising=False)

    with _client(tmp_path, monkeypatch) as client:
        for header_ip in ["10.10.10.10", "10.10.10.11"]:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "ops", "password": "wrong-password"},
                headers={"x-forwarded-for": header_ip},
            )
            assert response.status_code == 401

        locked = client.post(
            "/api/v1/auth/login",
            json={"username": "ops", "password": "wrong-password"},
            headers={"x-forwarded-for": "10.10.10.12"},
        )
        assert locked.status_code == 429

        still_locked = client.post(
            "/api/v1/auth/login",
            json={"username": "ops", "password": "ops123"},
            headers={"x-forwarded-for": "10.10.10.13"},
        )
        assert still_locked.status_code == 429
