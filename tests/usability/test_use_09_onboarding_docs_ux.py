"""
USABILITY-09: Onboarding, Documentation, UX Flows & Error Experience
The "first mile" experience: onboarding wizard, help system, error messages,
accessibility, multi-tab, ambient, image generation, integrations.
"""
import pytest
from tests.usability.conftest import *


class TestUseOnboardingWizard:
    """New user completes the onboarding wizard."""

    async def test_onboarding_status_check(self, U):
        """Platform checks whether onboarding has been completed."""
        r = await GET(U, "/api/onboarding/status")
        no_error(r, "onboarding status")
        d = j(r)
        uat("status field present",
            "completed" in d or "status" in d or "onboarded" in d or "complete" in d)

    async def test_onboarding_steps_loaded(self, U):
        """Onboarding wizard shows all steps to complete."""
        r = await GET(U, "/api/onboarding/steps")
        no_error(r, "onboarding steps")
        d = j(r)
        steps = d if isinstance(d, list) else d.get("steps", [])
        uat("steps returned", isinstance(steps, list))
        uat("has onboarding steps", len(steps) > 0)

    async def test_onboarding_themes_visible(self, U):
        """User can pick a color theme during onboarding."""
        r = await GET(U, "/api/onboarding/themes")
        no_error(r, "onboarding themes")
        d = j(r)
        themes = d if isinstance(d, list) else d.get("themes", [])
        uat("themes available", isinstance(themes, list))

    async def test_onboarding_complete_flow(self, U):
        """User completes onboarding — platform marks as done."""
        r = await POST(U, "/api/onboarding/complete", {
            "name": uid("NewUser"), "role": "developer",
            "use_cases": ["coding", "research"], "theme": "dark"
        })
        no_error(r, "complete onboarding")
        d = j(r)
        uat("onboarding completed", d.get("ok") is True or "completed" in d)

    async def test_onboarding_preferences_persist(self, U):
        """User's onboarding preferences are saved."""
        r = await PUT(U, "/api/onboarding/preferences", {
            "theme": "dark", "sidebar_compact": True,
            "default_agent": "brain", "auto_memory": True
        })
        no_error(r, "save onboarding preferences")

    async def test_onboarding_reset(self, U):
        """Admin can reset onboarding for testing."""
        r = await POST(U, "/api/onboarding/reset", {})
        no_error(r, "reset onboarding")

    async def test_profile_complete_onboarding(self, U):
        """Profile endpoint marks onboarding complete."""
        r = await POST(U, "/api/profile/complete-onboarding", {})
        no_error(r, "profile complete onboarding")


class TestUseDocumentationCenter:
    """User finds answers through the built-in documentation system."""

    async def test_quickstarts_load(self, U):
        """Quickstart guides appear for new users."""
        r = await GET(U, "/api/docs/quick-starts")
        no_error(r, "quickstarts")
        d = j(r)
        # Response: {"quick_starts": [...], "count": N}
        qstarts = (d.get("quick_starts") or d.get("quickstarts") or
                   d.get("items") or (d if isinstance(d, list) else []))
        uat("quickstarts returned", isinstance(qstarts, list))
        uat("has quickstart guides", len(qstarts) > 0)

    async def test_specific_quickstart_detail(self, U):
        """User clicks a quickstart to see full instructions."""
        r = await GET(U, "/api/docs/quick-starts")
        d = j(r)
        qs = d if isinstance(d, list) else d.get("quickstarts", [])
        if not qs: pytest.skip("No quickstarts")
        qid = qs[0].get("id", "qs_chat")
        r2 = await GET(U, f"/api/docs/quick-starts/{qid}")
        no_error(r2, "quickstart detail")

    async def test_features_documentation(self, U):
        """Features documentation panel loads all features."""
        r = await GET(U, "/api/docs/features")
        no_error(r, "features docs")
        d = j(r)
        features = d if isinstance(d, list) else d.get("features", [])
        uat("features returned", isinstance(features, list))

    async def test_faq_section(self, U):
        """FAQ section answers common questions."""
        r = await GET(U, "/api/docs/faq")
        no_error(r, "faq")
        d = j(r)
        # Response: {"faq": [...], "count": N}
        faqs = (d.get("faq") or d.get("faqs") or d.get("questions") or
                (d if isinstance(d, list) else []))
        uat("faqs returned", isinstance(faqs, list))
        uat("has faq items", len(faqs) > 0)

    async def test_keyboard_shortcuts_reference(self, U):
        """Keyboard shortcuts panel displays hotkeys."""
        r = await GET(U, "/api/docs/shortcuts")
        no_error(r, "shortcuts")
        d = j(r)
        shortcuts = d if isinstance(d, list) else d.get("shortcuts", [])
        uat("shortcuts returned", isinstance(shortcuts, list))

    async def test_documentation_search(self, U):
        """User searches documentation for 'memory' — relevant docs appear."""
        r = await GET(U, "/api/docs/search?q=memory")
        no_error(r, "docs search")
        d = j(r)
        results = d if isinstance(d, list) else d.get("results", [])
        uat("search results returned", isinstance(results, list))

    async def test_contextual_help(self, U):
        """Contextual help appears for the current pane."""
        for pane in ["chat", "memory", "builder", "analytics"]:
            r = await GET(U, f"/api/docs/contextual/{pane}")
            no_error(r, f"contextual help {pane}")
            d = j(r)
            uat(f"contextual help for {pane}", d.get("help") or d.get("content") or isinstance(d, dict))

    async def test_feedback_submission(self, U):
        """User can rate documentation helpfulness."""
        r = await POST(U, "/api/docs/feedback", {
            "doc_id": "qs_chat", "doc_type": "quickstart",
            "helpful": True, "comment": "Very clear instructions!"
        })
        no_error(r, "doc feedback")
        d = j(r)
        uat("feedback recorded", d.get("ok") is True or "id" in d)

    async def test_feature_specific_docs(self, U):
        """User looks up docs for a specific feature."""
        r = await GET(U, "/api/docs/features/memory")
        no_error(r, "feature specific docs")


class TestUseErrorExperience:
    """Platform gives helpful errors — never crashes or shows raw stack traces."""

    async def test_missing_required_field_helpful_message(self, U):
        """Creating an agent without a name gives a helpful message."""
        r = await POST(U, "/api/agents", {"model": "gemini-flash"})
        d = j(r)
        # Must not 500
        uat("no server crash on missing field", r.status_code < 500)

    async def test_invalid_task_id_graceful(self, U):
        """Fetching or patching a non-existent task returns a clean error."""
        # Tasks use PATCH for single-item access
        import httpx
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
            r = await c.patch("/api/tasks/this_task_does_not_exist_99999",
                              json={"title": "test"})
        uat("no server crash on bad task id", r.status_code < 500)
        # Must communicate failure gracefully — 200 with ok:false or 4xx
        uat("error communicated gracefully",
            r.status_code in [200, 400, 404, 405, 422])

    async def test_empty_chat_message_handled(self, U):
        """Sending empty message to chat doesn't crash."""
        r = await POST(U, "/api/chat", {"message": "", "agent": "brain", "session_id": uid()})
        uat("empty message handled", r.status_code < 500)

    async def test_very_long_input_handled(self, U):
        """Extremely long input doesn't crash the server."""
        r = await POST(U, "/api/memory/add", {
            "content": "A" * 50000, "source": "stress_test"
        })
        uat("long content handled", r.status_code < 500)

    async def test_nonexistent_endpoint_404(self, U):
        """Requesting a nonexistent endpoint gives 404."""
        r = await GET(U, "/api/this_pane_does_not_exist")
        uat("nonexistent endpoint is 404", r.status_code == 404)

    async def test_malformed_json_handled(self, U):
        """Malformed JSON body returns an error, not a crash."""
        import httpx
        async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:
            r = await c.post("/api/tasks", content=b"not valid json at all",
                             headers={"Content-Type": "application/json"})
            uat("malformed json handled gracefully", r.status_code < 500)

    async def test_delete_nonexistent_resource_handled(self, U):
        """Deleting a resource that doesn't exist is graceful."""
        r = await DELETE(U, "/api/tasks/nonexistent_task_999")
        uat("delete nonexistent handled", r.status_code < 500)


class TestUseMultiTab:
    """User works across multiple browser tabs simultaneously."""

    async def test_tabs_list(self, U):
        """User's open tabs are tracked."""
        r = await GET(U, "/api/multitab/tabs")
        no_error(r, "tabs list")
        d = j(r)
        tabs = d if isinstance(d, list) else d.get("tabs", [])
        uat("tabs returned", isinstance(tabs, list))

    async def test_create_tab(self, U):
        """User opens a new tab — recorded in state."""
        r = await POST(U, "/api/multitab/tabs", {
            "title": uid("NewTab"), "url": "/chat",
            "content": "chat_pane"
        })
        no_error(r, "create tab")
        d = j(r)
        tid = d.get("id") or d.get("tab_id")
        uat("tab created", bool(tid) or d.get("ok") is True)

        if tid:
            r2 = await POST(U, f"/api/multitab/tabs/{tid}/activate", {})
            no_error(r2, "activate tab")
            await DELETE(U, f"/api/multitab/tabs/{tid}")

    async def test_multitab_snapshot(self, U):
        """Current tab state can be snapshotted."""
        r = await POST(U, "/api/multitab/snapshot", {})
        no_error(r, "multitab snapshot")

    async def test_multitab_files(self, U):
        """User's open files tracked across tabs."""
        r = await GET(U, "/api/multitab/files")
        no_error(r, "multitab files")


class TestUseAmbientIntelligence:
    """Platform proactively helps with ambient intelligence."""

    async def test_ambient_health_check(self, U):
        """Ambient system health visible."""
        r = await GET(U, "/api/ambient/health")
        no_error(r, "ambient health")
        d = j(r)
        uat("health status returned", "status" in d or "healthy" in d or isinstance(d, dict))

    async def test_ambient_suggestions(self, U):
        """Platform proactively surfaces relevant suggestions."""
        r = await GET(U, "/api/ambient/suggestions")
        no_error(r, "ambient suggestions")
        d = j(r)
        suggestions = d if isinstance(d, list) else d.get("suggestions", [])
        uat("suggestions returned", isinstance(suggestions, list))

    async def test_ambient_scan_triggers(self, U):
        """User triggers an ambient context scan."""
        r = await POST(U, "/api/ambient/scan", {
            "context": {"current_pane": "builder", "file": "app.py"}
        })
        no_error(r, "ambient scan")
        d = j(r)
        uat("scan result returned", d.get("ok") is True or "insights" in d or isinstance(d, dict))

    async def test_ambient_health_history(self, U):
        """Ambient system health history visible."""
        r = await GET(U, "/api/ambient/health/history")
        no_error(r, "ambient health history")


class TestUseImageGeneration:
    """User generates images within the platform."""

    async def test_image_gallery_loads(self, U):
        """Image gallery shows generated images."""
        r = await GET(U, "/api/imagegen/gallery")
        no_error(r, "image gallery")
        d = j(r)
        images = d if isinstance(d, list) else d.get("images", d.get("gallery", []))
        uat("gallery returned", isinstance(images, list))

    async def test_enhance_prompt(self, U):
        """User enhances an image prompt with AI assistance."""
        r = await POST(U, "/api/imagegen/enhance-prompt", {
            "prompt": "a cat sitting on a laptop"
        })
        no_error(r, "enhance prompt")
        d = j(r)
        uat("enhanced prompt returned", "enhanced" in d or "prompt" in d or "ok" in d)

    async def test_generate_image_request(self, U):
        """User requests image generation — job queued."""
        r = await POST(U, "/api/imagegen/generate", {
            "prompt": "A futuristic city at sunset with flying cars",
            "model": "dall-e-3", "size": "1024x1024"
        })
        no_error(r, "generate image")
        d = j(r)
        uat("generation job queued", d.get("ok") is not None or "job_id" in d or "url" in d)

    async def test_style_transfer(self, U):
        """User applies a style to an existing image concept."""
        r = await POST(U, "/api/imagegen/style-transfer", {
            "prompt": "a landscape", "style": "van-gogh", "strength": 0.7
        })
        no_error(r, "style transfer")


class TestUseIntegrations:
    """User connects third-party services via integrations."""

    async def test_integrations_list(self, U):
        """Available integrations visible in the integration hub."""
        r = await GET(U, "/api/integrations")
        no_error(r, "integrations list")
        d = j(r)
        ints = d if isinstance(d, list) else d.get("integrations", [])
        uat("integrations returned", isinstance(ints, list))

    async def test_integration_rules(self, U):
        """User creates an automation rule via integrations."""
        r = await POST(U, "/api/integrations/rules", {
            "name": uid("AutoRule"), "trigger": "task.completed",
            "action": "notify_slack", "condition": {"priority": "high"}
        })
        no_error(r, "create integration rule")

    async def test_docs_generation(self, U):
        """Auto-generate documentation from code/specs."""
        r = await POST(U, "/api/integrations/docs/generate", {
            "source": "openapi", "format": "markdown",
            "agent_id": "builder"
        })
        no_error(r, "docs generation")
