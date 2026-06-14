"""C21-4 — atomic two-doc Fulfillment save."""
from tests._constants import TENANT_A_ID


def test_update_fulfillment_writes_both_docs(client, pro_plan_tenant_a):
    payload = {
        "restaurant": {
            "pickup_enabled": True,
            "delivery_enabled": True,
            "avg_prep_time_minutes": 25,
            "delivery_radius_miles": 7,
            "delivery_zip_codes": ["60540", "60563"],
        },
        "config": {"delivery_enabled": True, "delivery_minimum": 2000},
    }
    r = client.put(
        f"/api/restaurants/{TENANT_A_ID}/fulfillment",
        json=payload,
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["restaurant"]["pickup_enabled"] is True
    assert body["restaurant"]["delivery_radius_miles"] == 7
    assert body["restaurant"]["delivery_zip_codes"] == ["60540", "60563"]
    assert body["config"]["delivery_minimum"] == 2000


def test_update_fulfillment_rejects_other_tenant(client, two_tenant_with_memberships):
    r = client.put(
        f"/api/restaurants/{TENANT_A_ID}/fulfillment",
        json={"restaurant": {"pickup_enabled": False}},
        headers={"Authorization": "Bearer tenant_b"},
    )
    assert r.status_code in (403, 404)


def test_update_fulfillment_plan_gates_delivery(client, two_tenant_with_memberships):
    # tenant_a has no plan set -> STARTER -> delivery must be stripped; pickup applies.
    r = client.put(
        f"/api/restaurants/{TENANT_A_ID}/fulfillment",
        json={
            "restaurant": {"delivery_enabled": True, "pickup_enabled": True},
            "config": {"delivery_enabled": True},
        },
        headers={"Authorization": "Bearer tenant_a"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["restaurant"].get("delivery_enabled") in (None, False)
    assert body["restaurant"]["pickup_enabled"] is True
