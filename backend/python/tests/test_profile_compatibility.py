from unittest import TestCase

from app.ingestion.profiles import profile_compatible, profile_signature


class ProfileCompatibilityTest(TestCase):
    def test_ready_non_code_profile_accepts_code_routing_prompt_update(self):
        config = {'categories': ['cybersecurity', 'networking'], 'promptVersion': 'batched-category-label-discovery-code-routing-2'}
        previous = profile_signature({**config, 'promptVersion': 'batched-category-label-discovery-1'})
        profile = {'model_configuration': previous, 'settings': {'entityTypes': [], 'relationshipTypes': []}}
        self.assertTrue(profile_compatible(profile, config))
        self.assertFalse(profile_compatible(profile, {**config, 'categories': ['code_repository']}))
