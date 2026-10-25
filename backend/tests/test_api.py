import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.connection import connect
from app.main import create_app


CATALOG = Path(__file__).resolve().parents[1] / "fixtures" / "metric_definitions.json"
SNAPSHOT_VALUES = {
    "HML_valuation_zscore": 1.6,
    "HML_return_1m": -0.032,
    "HML_return_3m": -0.071,
    "HML_return_12m": -0.045,
    "RMW_return_3m": 0.042,
    "RMW_return_12m": 0.083,
    "MOM_return_1m": -0.025,
    "MOM_return_12m": 0.124,
    "treasury_yield_10y": 0.042,
}


class WorkbenchApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "workbench.sqlite"
        self.app = create_app(self.database_path, CATALOG, convergence_root=Path(self.temp_dir.name))
        self.client = TestClient(self.app)
        self.client.__enter__()
        response = self.client.post(
            "/api/v1/evidence/snapshots",
            json={
                "name": "October sample",
                "asOf": "2026-10-01",
                "values": SNAPSHOT_VALUES,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.snapshot = response.json()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp_dir.cleanup()

    @staticmethod
    def profile_payload(field_keys=None):
        return {
            "name": "HML valuation sensitivity",
            "fieldKeys": field_keys or ["HML_valuation_zscore"],
            "settings": {
                "strategy": "explicit",
                "explicitValues": [0.5, 1.0, 2.0],
            },
            "combinationMode": "one-at-a-time",
        }

    def test_health_and_metric_catalog(self):
        self.assertEqual(self.client.get("/api/v1/health").json(), {"status": "ok"})
        response = self.client.get("/api/v1/evidence/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item["key"] == "HML_valuation_zscore" for item in response.json()))

    def test_snapshot_profile_preview_and_generation_provenance(self):
        profile_response = self.client.post(
            "/api/v1/mutation-profiles", json=self.profile_payload()
        )
        self.assertEqual(profile_response.status_code, 201, profile_response.text)
        profile = profile_response.json()

        preview_response = self.client.post(
            "/api/v1/variants/preview",
            json={
                "snapshotId": self.snapshot["id"],
                "fieldKeys": profile["fieldKeys"],
                "settings": profile["settings"],
                "combinationMode": profile["combinationMode"],
            },
        )
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()
        self.assertEqual(preview["totalCount"], 3)
        self.assertEqual(preview["variants"][0]["values"]["HML_valuation_zscore"], 0.5)
        with connect(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM variant_batches").fetchone()[0], 0)

        generated_response = self.client.post(
            "/api/v1/variants/generate",
            json={"snapshotId": self.snapshot["id"], "profileId": profile["id"]},
        )
        self.assertEqual(generated_response.status_code, 201, generated_response.text)
        generated = generated_response.json()
        self.assertEqual(generated["totalGenerated"], 3)

        batch_response = self.client.get(
            "/api/v1/variants", params={"batch_id": generated["batchId"]}
        )
        self.assertEqual(batch_response.status_code, 200, batch_response.text)
        batch = batch_response.json()
        self.assertEqual(batch["snapshotId"], self.snapshot["id"])
        self.assertEqual(batch["profileSnapshot"]["name"], profile["name"])
        self.assertEqual(len(batch["variants"]), 3)

        delete_response = self.client.delete(f"/api/v1/mutation-profiles/{profile['id']}")
        self.assertEqual(delete_response.status_code, 204)
        retained_batch = self.client.get(
            "/api/v1/variants", params={"batch_id": generated["batchId"]}
        ).json()
        self.assertIsNone(retained_batch["profileId"])
        self.assertEqual(retained_batch["profileSnapshot"]["name"], profile["name"])

    def test_profile_compatibility_and_invalid_mutation(self):
        profile_response = self.client.post(
            "/api/v1/mutation-profiles",
            json=self.profile_payload(["MOM_return_12m"]),
        )
        self.assertEqual(profile_response.status_code, 201, profile_response.text)
        profile = profile_response.json()
        validation = self.client.post(
            f"/api/v1/mutation-profiles/{profile['id']}/validate",
            params={"snapshot_id": self.snapshot["id"]},
        )
        self.assertEqual(validation.status_code, 200)
        self.assertTrue(validation.json()["compatible"])

        bad_preview = self.client.post(
            "/api/v1/variants/preview",
            json={
                "snapshotId": self.snapshot["id"],
                "fieldKeys": ["does_not_exist"],
                "settings": self.profile_payload()["settings"],
                "combinationMode": "one-at-a-time",
            },
        )
        self.assertEqual(bad_preview.status_code, 422)
        self.assertEqual(bad_preview.json()["detail"]["issues"][0]["code"], "field_missing")

    def test_invalid_snapshot_and_unknown_profile_are_not_found(self):
        self.assertEqual(
            self.client.get("/api/v1/evidence/snapshots/unknown").status_code,
            404,
        )
        response = self.client.post(
            "/api/v1/variants/generate",
            json={"snapshotId": self.snapshot["id"], "profileId": "unknown"},
        )
        self.assertEqual(response.status_code, 404)

    def test_list_and_get_snapshots(self):
        response = self.client.get("/api/v1/evidence/snapshots", params={"limit": 1, "offset": 0})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["snapshots"], [self.snapshot])
        fetched = self.client.get(f"/api/v1/evidence/snapshots/{self.snapshot['id']}")
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json(), self.snapshot)
        self.assertEqual(
            self.client.get("/api/v1/evidence/snapshots", params={"offset": 1}).json()["snapshots"], []
        )
        self.assertEqual(
            self.client.get("/api/v1/evidence/snapshots", params={"limit": 0}).status_code, 422
        )

    def test_list_get_and_update_profiles(self):
        self.assertEqual(self.client.get("/api/v1/mutation-profiles").json(), {"profiles": [], "total": 0})
        created = self.client.post("/api/v1/mutation-profiles", json=self.profile_payload())
        self.assertEqual(created.status_code, 201, created.text)
        profile = created.json()
        path = f"/api/v1/mutation-profiles/{profile['id']}"
        fetched = self.client.get(path)
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json(), profile)
        listing = self.client.get("/api/v1/mutation-profiles")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json(), {"profiles": [profile], "total": 1})
        changes = self.profile_payload(["MOM_return_12m"])
        changes["name"] = "Updated momentum profile"
        changes["settings"]["explicitValues"] = [-0.02, 0.03]
        updated = self.client.put(path, json=changes)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["id"], profile["id"])
        for key in ("name", "fieldKeys", "combinationMode"):
            self.assertEqual(updated.json()[key], changes[key])
        self.assertEqual(updated.json()["settings"]["explicitValues"], [-0.02, 0.03])
        self.assertEqual(self.client.get(path).json(), updated.json())
        self.assertEqual(self.client.get("/api/v1/mutation-profiles/unknown").status_code, 404)
        self.assertEqual(self.client.put("/api/v1/mutation-profiles/unknown", json=changes).status_code, 404)
        self.assertEqual(self.client.delete("/api/v1/mutation-profiles/unknown").status_code, 404)
        invalid = {**changes, "fieldKeys": ["unknown"]}
        self.assertEqual(self.client.put(path, json=invalid).status_code, 422)
        self.assertEqual(self.client.get(path).json(), updated.json())

    def test_get_variant_and_list_batch_variants(self):
        generated = self.client.post("/api/v1/variants/generate", json={
            "snapshotId": self.snapshot["id"],
            "fieldKeys": ["HML_valuation_zscore"],
            "settings": self.profile_payload()["settings"],
            "combinationMode": "one-at-a-time",
        })
        self.assertEqual(generated.status_code, 201, generated.text)
        batch_id = generated.json()["batchId"]
        response = self.client.get(f"/api/v1/variants/batch/{batch_id}/variants")
        self.assertEqual(response.status_code, 200, response.text)
        variants = response.json()
        self.assertEqual(len(variants), 3)
        self.assertEqual([variant["values"]["HML_valuation_zscore"] for variant in variants], [0.5, 1.0, 2.0])
        fetched = self.client.get(f"/api/v1/variants/{variants[0]['id']}")
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json(), variants[0])
        self.assertEqual(self.client.get("/api/v1/variants/unknown").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/variants/batch/unknown/variants").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/variants", params={"batch_id": "unknown"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
