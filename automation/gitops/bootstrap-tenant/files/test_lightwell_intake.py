"""Unit tests for intake decisions. No cluster."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import unittest
from unittest import mock

import lightwell_intake as intake


HERE = pathlib.Path(__file__).resolve().parent


def _load_reconcile():
    spec = importlib.util.spec_from_file_location("nexus_reconcile", HERE / "nexus-reconcile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AcceptEventTest(unittest.TestCase):
    def test_non_rhlw_creates_nothing(self):
        key = intake.event_key("g", "com.acme", "demo", "1.0.0")
        self.assertFalse(intake.accept_event("1.0.0", key, set()))

    def test_first_rhlw_is_accepted(self):
        key = intake.event_key("g", "com.h2database", "h2", "2.2.224.rhlw-00001")
        self.assertTrue(intake.accept_event("2.2.224.rhlw-00001", key, set()))

    def test_duplicate_is_not_accepted(self):
        key = intake.event_key("g", "com.h2database", "h2", "2.2.224.rhlw-00001")
        self.assertFalse(intake.accept_event("2.2.224.rhlw-00001", key, {key}))

    def test_pipeline_run_name_is_a_dns_label(self):
        name = intake.pipeline_run_name("jackson-databind", "2.13.5.rhlw-00001")
        self.assertEqual(name, "lw-jackson-databind-2-13-5-rhlw-00001")
        self.assertLessEqual(len(name), 63)
        self.assertNotIn(".", name)


class PlanTest(unittest.TestCase):
    def test_two_platform_apps_and_a_renovate_skip(self):
        found = [
            intake.AppPolicy("wire-transfer-svc", {"remediation_owner": "ao", "approval": "needs_approval"}, True),
            intake.AppPolicy("benefits-mgmt-app", {"remediation_owner": "ao", "approval": "auto_approve"}, True),
            intake.AppPolicy("report-generator-app", {"remediation_owner": "renovate"}, True),
        ]
        plan = intake.plan_apps(found)
        self.assertTrue(plan.ok)
        self.assertEqual([a.name for a in plan.platform], ["wire-transfer-svc", "benefits-mgmt-app"])
        self.assertEqual([a.name for a in plan.skipped], ["report-generator-app"])
        self.assertIn("report-generator-app", plan.comment)
        self.assertIn("needs_approval", plan.comment)

    def test_missing_policy_does_not_count_as_platform(self):
        plan = intake.plan_apps([intake.AppPolicy("wire-transfer-svc", None, False)])
        self.assertFalse(plan.ok)
        self.assertEqual(plan.invalid, ["wire-transfer-svc"])
        self.assertEqual(plan.platform, [])

    def test_empty_blast_radius_fails(self):
        plan = intake.plan_apps([])
        self.assertFalse(plan.ok)
        self.assertIn("No applications", plan.comment)


class RenovateJobTest(unittest.TestCase):
    def test_job_does_not_extend_the_upstream_preset(self):
        job = intake.renovate_job(
            app="benefits-mgmt-app",
            gitlab_group="acme-demo",
            namespace="user-demo-renovate",
            gitlab_endpoint="https://gitlab.example/api/v4",
            nexus_host="nexus-lightwell-nexus-demo.apps.example.com",
            nexus_password="secret",
            gav="org.apache.commons:commons-text:1.9.rhlw-00002",
        )
        inline = job["spec"]["renovateConfig"]["inline"]
        self.assertNotIn("github>lightwell", inline)
        self.assertNotIn("packages.redhat.com", inline)
        self.assertIn("nexus-lightwell-nexus-demo.apps.example.com/repository/maven-public", inline)
        cfg = json.loads(inline)
        self.assertEqual(cfg["prBodyTemplate"], "{{{notes}}}")
        body = cfg["prBodyNotes"][0]
        self.assertIn("<!-- lw:validation:start -->", body)
        self.assertNotIn("{{#each upgrades}}", body)
        self.assertIn('"artifact_id": "{{{depName}}}"', body)
        self.assertEqual(job["spec"]["discoveryFilters"], ["acme-demo/benefits-mgmt-app"])

    def test_renovate_owner_produces_no_job(self):
        plan = intake.plan_apps(
            [intake.AppPolicy("report-generator-app", {"remediation_owner": "renovate"}, True)]
        )
        self.assertEqual(plan.platform, [])
        self.assertTrue(plan.ok)


class RunIntakeTest(unittest.TestCase):
    def test_fakes_open_two_children_and_skip_renovate(self):
        created = []

        def create(_url, payload):
            created.append(payload)
            return f"INC{len(created):04d}"

        comments = []

        def comment(_url, number, text):
            comments.append((number, text))

        def policy(_url, _token, path):
            if path.endswith("report-generator-app"):
                return {"remediation_owner": "renovate"}, True
            if path.endswith("wire-transfer-svc"):
                return {"remediation_owner": "ao", "approval": "needs_approval"}, True
            return {"remediation_owner": "ao", "approval": "auto_approve"}, True

        with (
            mock.patch.object(intake, "snow_create", create),
            mock.patch.object(intake, "snow_comment", comment),
            mock.patch.object(intake, "gitlab_policy", policy),
            mock.patch.object(
                intake,
                "tpa_affected",
                lambda *_a, **_k: ["wire-transfer-svc", "benefits-mgmt-app", "report-generator-app"],
            ),
        ):
            result = intake.run_intake(
                guid="demo",
                group="org.apache.commons",
                artifact="commons-text",
                version="1.9.rhlw-00002",
                app_names=["wire-transfer-svc", "benefits-mgmt-app", "report-generator-app"],
                gitlab_group="acme-demo",
                gitlab_url="https://gitlab.example",
                gitlab_token="t",
                tpa_url="https://tpa.example",
                tpa_token="t",
                snow_url="http://snow",
                renovate_namespace="user-demo-renovate",
                gitlab_endpoint="https://gitlab.example/api/v4",
                nexus_host="nexus.example",
                nexus_password="pw",
            )
        self.assertTrue(result.ok)
        self.assertEqual(set(result.children), {"wire-transfer-svc", "benefits-mgmt-app"})
        self.assertEqual(len(result.jobs), 2)
        self.assertTrue(all("report-generator" not in j["metadata"]["name"] for j in result.jobs))
        self.assertEqual(created[0]["caller_id"], "lightwell-intake")
        self.assertNotIn("merge", comments[0][1].lower())
        self.assertIn("report-generator-app", comments[0][1])

    def test_empty_tpa_fails_without_a_job(self):
        with (
            mock.patch.object(intake, "snow_create", lambda *_a, **_k: "INC0001"),
            mock.patch.object(intake, "snow_comment", lambda *_a, **_k: None),
            mock.patch.object(intake, "tpa_affected", lambda *_a, **_k: []),
        ):
            result = intake.run_intake(
                guid="demo",
                group="com.h2database",
                artifact="h2",
                version="2.2.224.rhlw-00001",
                app_names=["wire-transfer-svc"],
                gitlab_group="acme-demo",
                gitlab_url="https://gitlab.example",
                gitlab_token="t",
                tpa_url="https://tpa.example",
                tpa_token="t",
                snow_url="http://snow",
                renovate_namespace="ns",
                gitlab_endpoint="https://gitlab.example/api/v4",
                nexus_host="nexus.example",
                nexus_password="pw",
            )
        self.assertFalse(result.ok)
        self.assertEqual(result.jobs, [])
        self.assertEqual(result.parent, "INC0001")


class WebhookTargetTest(unittest.TestCase):
    def test_drive_selects_the_host(self):
        reconcile = _load_reconcile()
        tekton = reconcile.webhook_targets(
            "tekton",
            "http://sdlc-remediation-demo.aap.svc:5000/",
            "https://sdlc-remediation-demo-aap.apps.example.com/",
            "http://el-lightwell-intake.build-demo.svc:8080",
            "https://lightwell-intake-demo.apps.example.com",
        )
        ao = reconcile.webhook_targets(
            "ao",
            "http://sdlc-remediation-demo.aap.svc:5000/",
            "https://sdlc-remediation-demo-aap.apps.example.com/",
            "http://el-lightwell-intake.build-demo.svc:8080",
            "https://lightwell-intake-demo.apps.example.com",
        )
        self.assertIn("el-lightwell-intake", tekton[0])
        self.assertIn("sdlc-remediation-demo", ao[0])
        self.assertNotIn("el-lightwell-intake", ao[0])


class AffectedTest(unittest.TestCase):
    def test_purl_match(self):
        apps = intake.affected_from_packages(
            {
                "wire-transfer-svc": '{"purl":"pkg:maven/com.h2database/h2@2.2.219"}',
                "benefits-mgmt-app": '{"purl":"pkg:maven/org.flywaydb/flyway-core@9.0.0"}',
            },
            "com.h2database",
            "h2",
        )
        self.assertEqual(apps, ["wire-transfer-svc"])


if __name__ == "__main__":
    unittest.main()
